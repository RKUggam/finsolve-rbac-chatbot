"""Token counting, cost computation, and budget alerting.

Cost is computed from configurable per-1K-token rates (see `.env`). A process-
level `CostTracker` accumulates spend per UTC day and raises alerts when either
a single request or the running daily total breaches its budget. Alerts are
logged at WARNING and, if `COST_ALERT_WEBHOOK_URL` is set, POSTed to that webhook.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import tiktoken

from app.config import get_settings
from app.logging_config import get_logger
from app.rag.schemas import TokenUsage

logger = get_logger(__name__)

# gpt-4o family uses the o200k_base encoding; fall back to cl100k_base otherwise.
try:
    _ENCODER = tiktoken.get_encoding("o200k_base")
except Exception:  # noqa: BLE001
    _ENCODER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Approximate token count for a string (used for embedding-cost estimates)."""
    if not text:
        return 0
    return len(_ENCODER.encode(text))


def compute_cost(input_tokens: int, output_tokens: int, embedding_tokens: int = 0) -> float:
    """Compute USD cost from token counts using configured rates."""
    s = get_settings()
    return round(
        (input_tokens / 1000) * s.cost_input_per_1k
        + (output_tokens / 1000) * s.cost_output_per_1k
        + (embedding_tokens / 1000) * s.cost_embedding_per_1k,
        6,
    )


def build_usage(input_tokens: int, output_tokens: int, embedding_tokens: int = 0) -> TokenUsage:
    """Assemble a TokenUsage record with computed cost."""
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        embedding_tokens=embedding_tokens,
        total_tokens=input_tokens + output_tokens + embedding_tokens,
        cost_usd=compute_cost(input_tokens, output_tokens, embedding_tokens),
    )


class CostTracker:
    """Thread-safe accumulator of daily spend with budget alerting."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = datetime.now(UTC).date()
        self._daily_cost = 0.0
        self._daily_requests = 0

    def _roll_day_if_needed(self) -> None:
        today = datetime.now(UTC).date()
        if today != self._day:
            logger.info(
                "cost_daily_rollover",
                day=str(self._day),
                total_usd=round(self._daily_cost, 4),
                requests=self._daily_requests,
            )
            self._day = today
            self._daily_cost = 0.0
            self._daily_requests = 0

    def record(self, usage: TokenUsage, *, username: str = "unknown") -> None:
        """Record a request's usage and evaluate budget thresholds."""
        s = get_settings()
        with self._lock:
            self._roll_day_if_needed()
            self._daily_cost += usage.cost_usd
            self._daily_requests += 1
            daily_total = self._daily_cost

        if usage.cost_usd >= s.cost_per_request_alert_usd:
            self._alert(
                "per_request_cost_exceeded",
                f"Request cost ${usage.cost_usd:.4f} exceeded per-request cap "
                f"${s.cost_per_request_alert_usd:.4f}",
                username=username,
                request_cost_usd=usage.cost_usd,
            )
        if daily_total >= s.cost_daily_budget_usd:
            self._alert(
                "daily_budget_exceeded",
                f"Daily spend ${daily_total:.2f} exceeded budget "
                f"${s.cost_daily_budget_usd:.2f}",
                daily_total_usd=round(daily_total, 4),
            )

    @property
    def daily_cost(self) -> float:
        with self._lock:
            self._roll_day_if_needed()
            return round(self._daily_cost, 6)

    def _alert(self, event: str, message: str, **fields: object) -> None:
        logger.warning("cost_alert", event=event, message=message, **fields)
        webhook = get_settings().cost_alert_webhook_url
        if webhook:
            self._post_webhook(webhook, message)

    @staticmethod
    def _post_webhook(url: str, message: str) -> None:
        try:
            import httpx

            httpx.post(url, json={"text": f":rotating_light: FinSolve cost alert: {message}"}, timeout=5)
        except Exception as exc:  # noqa: BLE001 - alerting must never break the request
            logger.warning("cost_alert_webhook_failed", error=str(exc))


# Process-wide singleton.
cost_tracker = CostTracker()
