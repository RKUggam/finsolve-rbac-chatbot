"""Prometheus metrics, exposed at `/metrics` for Azure Monitor / Grafana scraping."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

CHAT_REQUESTS = Counter(
    "finsolve_chat_requests_total",
    "Total chat requests handled.",
    labelnames=("role", "status"),
)

CHAT_BLOCKED = Counter(
    "finsolve_chat_blocked_total",
    "Chat requests blocked by guardrails.",
    labelnames=("reason",),
)

TOKENS_USED = Counter(
    "finsolve_tokens_total",
    "LLM tokens consumed.",
    labelnames=("kind",),  # input | output | embedding
)

COST_USD = Counter(
    "finsolve_cost_usd_total",
    "Cumulative estimated LLM cost in USD.",
)

CHAT_LATENCY = Histogram(
    "finsolve_chat_latency_seconds",
    "End-to-end chat request latency.",
    buckets=(0.25, 0.5, 1, 2, 4, 8, 16, 32),
)

RETRIEVED_DOCS = Histogram(
    "finsolve_retrieved_docs",
    "Number of documents retrieved per query.",
    buckets=(0, 1, 2, 3, 5, 8, 13),
)
