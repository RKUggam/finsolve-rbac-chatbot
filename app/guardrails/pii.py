"""PII detection and redaction.

Uses Microsoft Presidio when available (spaCy-backed NER + recognisers) and
falls back to a fast regex layer for the highest-risk identifiers so the
guardrail still functions if the optional model is not installed.

Two entry points:
  * `redact()`   — mask PII in outbound text before it reaches the user/logs.
  * `contains_pii()` — boolean check (used for logging / metrics).
"""

from __future__ import annotations

import re

from app.logging_config import get_logger

logger = get_logger(__name__)

# High-signal regex fallbacks (always applied, cheap, deterministic).
_REGEX_PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "PHONE": re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3,5}\)?[\s-]?)\d{3}[\s-]?\d{4}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "PAN": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),  # Indian PAN
    "AADHAAR": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
}

try:  # pragma: no cover - exercised only when presidio is installed
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine

    _analyzer: AnalyzerEngine | None = AnalyzerEngine()
    _anonymizer: AnonymizerEngine | None = AnonymizerEngine()
    logger.info("presidio_pii_enabled")
except Exception as exc:  # noqa: BLE001 - optional dependency, degrade gracefully
    _analyzer = None
    _anonymizer = None
    logger.warning("presidio_unavailable_using_regex_fallback", error=str(exc))


def _regex_redact(text: str) -> tuple[str, bool]:
    found = False
    for label, pattern in _REGEX_PATTERNS.items():
        text, n = pattern.subn(f"<{label}_REDACTED>", text)
        found = found or n > 0
    return text, found


def redact(text: str) -> tuple[str, bool]:
    """Return `(redacted_text, pii_found)`."""
    if not text:
        return text, False

    pii_found = False
    if _analyzer is not None and _anonymizer is not None:
        try:
            results = _analyzer.analyze(text=text, language="en")
            if results:
                pii_found = True
                text = _anonymizer.anonymize(text=text, analyzer_results=results).text
        except Exception as exc:  # noqa: BLE001
            logger.warning("presidio_analyze_failed_fallback", error=str(exc))

    text, regex_found = _regex_redact(text)
    return text, pii_found or regex_found


def contains_pii(text: str) -> bool:
    """Cheap boolean PII check."""
    _, found = redact(text)
    return found
