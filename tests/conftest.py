"""Shared pytest fixtures and test environment setup.

These tests are hermetic: they never touch Azure OpenAI or Milvus. Anything that
would call an external service is monkeypatched in the individual test modules.
"""

from __future__ import annotations

import os

# Deterministic config for the whole test session (set before app.config import).
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault("GUARDRAILS_PII_ENABLED", "true")
os.environ.setdefault("GUARDRAILS_SCOPE_ENABLED", "true")

import pytest  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
