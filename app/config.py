"""Centralised, validated application configuration.

All settings are read from environment variables (or a local `.env` file) and
validated once at import time via `get_settings()`. Nothing else in the codebase
reads `os.environ` directly — this keeps configuration in a single, testable place.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Application ----
    app_env: str = "development"
    log_level: str = "INFO"
    jwt_secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # ---- Azure OpenAI ----
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"
    embedding_dim: int = 3072

    # ---- Generation ----
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024

    # ---- Milvus ----
    milvus_uri: str = "http://localhost:19530"
    milvus_token: str = ""
    milvus_collection: str = "finsolve_documents"
    milvus_db_name: str = "default"

    # ---- RAG ----
    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieval_top_k: int = 5
    data_dir: str = "data"

    # ---- Cost monitoring ----
    cost_input_per_1k: float = 0.0025
    cost_output_per_1k: float = 0.010
    cost_embedding_per_1k: float = 0.00013
    cost_daily_budget_usd: float = 25.0
    cost_per_request_alert_usd: float = 0.25
    cost_alert_webhook_url: str = ""

    # ---- Guardrails ----
    guardrails_pii_enabled: bool = True
    guardrails_scope_enabled: bool = True

    # ---- Tracing ----
    langchain_tracing_v2: bool = False
    langchain_project: str = "finsolve-rbac-chatbot"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def azure_openai_configured(self) -> bool:
        """True when the minimum Azure OpenAI credentials are present."""
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)

    def validate_runtime(self) -> None:
        """Fail fast on missing critical config in production."""
        if self.is_production:
            problems: list[str] = []
            if self.jwt_secret_key == "change-me-to-a-long-random-string":
                problems.append("JWT_SECRET_KEY must be set to a real secret in production")
            if not self.azure_openai_configured:
                problems.append("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY are required")
            if problems:
                raise RuntimeError("Invalid production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    """Return a cached, validated Settings singleton."""
    return Settings()
