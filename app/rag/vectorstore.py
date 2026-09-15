"""Milvus vector store wrapper.

Uses `langchain_milvus.Milvus`, which manages the collection schema for us
(a primary key `pk`, the dense embedding `vector`, the page content `text`, and
the document metadata). With `enable_dynamic_field=True`, every metadata key we
attach at ingestion (notably `department`, `source`, `title`) is stored as a
Milvus dynamic field, so RBAC filters like `department in ["finance","general"]`
push down into Milvus at search time instead of being applied client-side.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_milvus import Milvus

from app.config import get_settings
from app.rag.providers import get_embeddings


def _connection_args() -> dict[str, str]:
    settings = get_settings()
    args: dict[str, str] = {"uri": settings.milvus_uri, "db_name": settings.milvus_db_name}
    if settings.milvus_token:
        args["token"] = settings.milvus_token
    return args


def get_vector_store(drop_old: bool = False) -> Milvus:
    """Return a Milvus vector store bound to the configured collection.

    The collection is created lazily on first insert if it does not yet exist.
    Set `drop_old=True` from the ingestion job to rebuild the index from scratch.
    """
    settings = get_settings()
    return Milvus(
        embedding_function=get_embeddings(),
        collection_name=settings.milvus_collection,
        connection_args=_connection_args(),
        consistency_level="Bounded",
        drop_old=drop_old,
        auto_id=True,
        enable_dynamic_field=True,
        index_params={"metric_type": "COSINE", "index_type": "AUTOINDEX"},
    )


@lru_cache
def get_cached_vector_store() -> Milvus:
    """Cached vector store for request handling (reuses the Milvus connection)."""
    return get_vector_store(drop_old=False)
