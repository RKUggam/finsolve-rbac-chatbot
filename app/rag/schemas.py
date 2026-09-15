"""Shared data structures for the RAG pipeline and API layer."""

from __future__ import annotations

from pydantic import BaseModel


class Citation(BaseModel):
    """A source document surfaced to the user alongside an answer."""

    title: str
    source: str
    department: str
    snippet: str


class TokenUsage(BaseModel):
    """Token counts and computed USD cost for a single request."""

    input_tokens: int = 0
    output_tokens: int = 0
    embedding_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


class ChatResult(BaseModel):
    """Full result of answering one question."""

    answer: str
    citations: list[Citation] = []
    usage: TokenUsage = TokenUsage()
    blocked: bool = False
    block_reason: str | None = None
