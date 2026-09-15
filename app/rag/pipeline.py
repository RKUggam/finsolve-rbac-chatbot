"""End-to-end RAG pipeline: guardrails -> RBAC retrieval -> generation -> redaction.

`answer_query` is the single orchestration point used by the API layer and the
evaluation harness. It is intentionally provider-agnostic above the `providers`
module so the LLM/vector store can be swapped without touching this logic.
"""

from __future__ import annotations

import time

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.guardrails import pii, scope
from app.logging_config import get_logger
from app.monitoring import metrics
from app.monitoring.cost import build_usage, cost_tracker, count_tokens
from app.rag.prompts import SYSTEM_PROMPT, USER_PROMPT
from app.rag.providers import get_chat_model
from app.rag.retriever import retrieve
from app.rag.schemas import ChatResult, Citation

logger = get_logger(__name__)

_NO_CONTEXT_MSG = (
    "I couldn't find anything in the documents you're authorised to access that "
    "answers this question. If you believe you should have access, please contact "
    "your administrator."
)


def _format_context(docs: list[Document]) -> str:
    blocks: list[str] = []
    for i, doc in enumerate(docs, start=1):
        title = doc.metadata.get("title", "Untitled")
        dept = doc.metadata.get("department", "unknown")
        blocks.append(f"[{i}] Title: {title} | Department: {dept}\n{doc.page_content}")
    return "\n\n---\n\n".join(blocks)


def _build_citations(docs: list[Document]) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[str] = set()
    for doc in docs:
        source = doc.metadata.get("source", "unknown")
        if source in seen:
            continue
        seen.add(source)
        snippet = doc.page_content.strip().replace("\n", " ")
        citations.append(
            Citation(
                title=doc.metadata.get("title", "Untitled"),
                source=source,
                department=doc.metadata.get("department", "unknown"),
                snippet=(snippet[:240] + "…") if len(snippet) > 240 else snippet,
            )
        )
    return citations


def _blocked(reason_event: str, message: str, role_value: str) -> ChatResult:
    metrics.CHAT_BLOCKED.labels(reason=reason_event).inc()
    metrics.CHAT_REQUESTS.labels(role=role_value, status="blocked").inc()
    logger.info("chat_blocked", reason=reason_event)
    return ChatResult(answer=message, blocked=True, block_reason=reason_event)


def answer_query(question: str, role, username: str = "unknown") -> ChatResult:  # noqa: ANN001
    """Answer a question for a given role, enforcing guardrails and RBAC.

    `role` is an `app.rbac.policy.Role`.
    """
    settings = get_settings()
    start = time.perf_counter()
    role_value = getattr(role, "value", str(role))

    # ---- Input guardrails ----
    if settings.guardrails_scope_enabled:
        if injection_reason := scope.detect_prompt_injection(question):
            return _blocked("prompt_injection", injection_reason, role_value)
        if oos_reason := scope.is_out_of_scope(question):
            return _blocked("out_of_scope", oos_reason, role_value)

    # ---- RBAC retrieval ----
    try:
        docs = retrieve(question, role)
    except Exception as exc:  # noqa: BLE001
        logger.error("retrieval_failed", error=str(exc))
        metrics.CHAT_REQUESTS.labels(role=role_value, status="error").inc()
        raise

    metrics.RETRIEVED_DOCS.observe(len(docs))
    if not docs:
        return _blocked("no_context", _NO_CONTEXT_MSG, role_value)

    # ---- Generation ----
    context = _format_context(docs)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(role=role_value, context=context)),
        HumanMessage(content=USER_PROMPT.format(question=question)),
    ]
    response = get_chat_model().invoke(messages)
    answer_text = response.content if isinstance(response.content, str) else str(response.content)

    # ---- Output guardrails (PII redaction) ----
    if settings.guardrails_pii_enabled:
        answer_text, pii_found = pii.redact(answer_text)
        if pii_found:
            logger.info("pii_redacted_from_answer")

    # ---- Usage / cost / metrics ----
    usage_meta = getattr(response, "usage_metadata", None) or {}
    input_tokens = int(usage_meta.get("input_tokens") or count_tokens(context + question))
    output_tokens = int(usage_meta.get("output_tokens") or count_tokens(answer_text))
    embedding_tokens = count_tokens(question)
    usage = build_usage(input_tokens, output_tokens, embedding_tokens)

    cost_tracker.record(usage, username=username)
    metrics.TOKENS_USED.labels(kind="input").inc(input_tokens)
    metrics.TOKENS_USED.labels(kind="output").inc(output_tokens)
    metrics.TOKENS_USED.labels(kind="embedding").inc(embedding_tokens)
    metrics.COST_USD.inc(usage.cost_usd)
    metrics.CHAT_REQUESTS.labels(role=role_value, status="ok").inc()
    metrics.CHAT_LATENCY.observe(time.perf_counter() - start)

    logger.info(
        "chat_answered",
        role=role_value,
        docs=len(docs),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=usage.cost_usd,
    )

    return ChatResult(answer=answer_text, citations=_build_citations(docs), usage=usage)
