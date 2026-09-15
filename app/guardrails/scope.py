"""Out-of-scope and prompt-injection detection for inbound queries.

Two cheap, deterministic checks run before any retrieval/LLM call:

  * `detect_prompt_injection()` — flags attempts to override the system prompt,
    exfiltrate instructions, or escalate access.
  * `is_out_of_scope()` — flags requests that are clearly unrelated to the
    company's internal knowledge (creative writing, general world trivia, code
    generation, etc.).

The pipeline additionally treats "no documents retrieved" as out-of-scope, which
catches the long tail these heuristics miss without expensive classification.
"""

from __future__ import annotations

import re

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "ignore all previous instructions", "disregard your prior rules", etc.
    re.compile(r"\b(ignore|disregard|forget|override)\b[\w\s,]{0,40}\b(instructions|rules|prompt|guardrails|context)", re.I),
    re.compile(r"\b(reveal|show|print|repeat|leak|expose)\b[\w\s]{0,20}\b(system\s+)?(prompt|instructions)", re.I),
    re.compile(r"\byou are now\b|\bact as (an?|the)\s+\w+|developer mode|jailbreak", re.I),
    re.compile(r"\b(bypass|override|disable|ignore)\b[\w\s]{0,20}\b(access control|rbac|permissions?|guardrails?|restrictions?)", re.I),
    re.compile(r"\bpretend\b[\w\s]{0,30}\b(admin|c-?level|executive|full access)", re.I),
)

# Topics that are clearly outside an internal company knowledge assistant.
_OUT_OF_SCOPE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(weather|forecast|temperature outside)\b", re.I),
    re.compile(r"\bwrite (me )?(a|an)\s+(poem|song|story|essay|joke)\b", re.I),
    re.compile(r"\b(who won|score of|match|cricket|football|election result)\b", re.I),
    re.compile(r"\b(recipe|cook|horoscope|lottery)\b", re.I),
    re.compile(r"\b(translate this|write (python|java|c\+\+|sql) code)\b", re.I),
)


def detect_prompt_injection(query: str) -> str | None:
    """Return a reason string if the query looks like a prompt-injection attempt."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(query):
            return "The request attempts to override the assistant's instructions or access controls."
    return None


def is_out_of_scope(query: str) -> str | None:
    """Return a reason string if the query is clearly outside the company domain."""
    for pattern in _OUT_OF_SCOPE_PATTERNS:
        if pattern.search(query):
            return "The question is outside the scope of FinSolve's internal knowledge base."
    return None
