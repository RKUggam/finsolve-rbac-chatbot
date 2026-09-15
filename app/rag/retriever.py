"""RBAC-aware document retrieval.

The retriever translates a user's role into a Milvus filter expression so that
*only* permitted departments are ever searched. Access control happens at the
data layer — the LLM never even sees documents the user is not allowed to read.
"""

from __future__ import annotations

from langchain_core.documents import Document

from app.config import get_settings
from app.rbac.policy import Role, allowed_department_values
from app.rag.vectorstore import get_cached_vector_store


def build_rbac_filter(role: Role) -> str:
    """Build a Milvus boolean expression limiting results to allowed departments."""
    departments = allowed_department_values(role)
    quoted = ", ".join(f'"{d}"' for d in departments)
    return f"department in [{quoted}]"


def retrieve(query: str, role: Role, top_k: int | None = None) -> list[Document]:
    """Return the top-k documents the given role is permitted to see."""
    settings = get_settings()
    k = top_k or settings.retrieval_top_k
    store = get_cached_vector_store()
    expr = build_rbac_filter(role)
    return store.similarity_search(query=query, k=k, expr=expr)
