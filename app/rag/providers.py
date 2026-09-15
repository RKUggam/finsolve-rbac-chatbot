"""Azure OpenAI client factories (chat + embeddings).

Centralising construction here means the deployment names, API version, and
endpoint are read from settings in exactly one place, and tests can monkeypatch
these factories to inject fakes.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from app.config import get_settings


@lru_cache
def get_embeddings() -> AzureOpenAIEmbeddings:
    """Return a cached Azure OpenAI embeddings client."""
    settings = get_settings()
    return AzureOpenAIEmbeddings(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_deployment=settings.azure_openai_embedding_deployment,
    )


@lru_cache
def get_chat_model() -> AzureChatOpenAI:
    """Return a cached Azure OpenAI chat client."""
    settings = get_settings()
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_deployment=settings.azure_openai_chat_deployment,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
