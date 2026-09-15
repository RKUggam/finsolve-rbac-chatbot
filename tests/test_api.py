"""API + auth integration via FastAPI TestClient (pipeline mocked)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_module
from app.main import app
from app.rag.schemas import ChatResult, Citation, TokenUsage


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient, username: str) -> None:
    resp = client.post("/auth/login", json={"username": username, "password": "FinSolve@2024"})
    assert resp.status_code == 200, resp.text


def test_chat_requires_authentication(client: TestClient):
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 401


def test_login_bad_credentials(client: TestClient):
    resp = client.post("/auth/login", json={"username": "cfo", "password": "nope"})
    assert resp.status_code == 401


def test_authenticated_chat_returns_answer(client: TestClient, monkeypatch):
    fake = ChatResult(
        answer="Revenue grew 25%.",
        citations=[Citation(title="Financial Summary", source="financial_summary.md",
                            department="finance", snippet="revenue grew by 25%")],
        usage=TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120, cost_usd=0.001),
    )
    monkeypatch.setattr(chat_module, "answer_query", lambda *a, **k: fake)

    _login(client, "finance.lead")
    resp = client.post("/api/chat", json={"message": "revenue growth?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Revenue grew 25%."
    assert body["role"] == "finance"
    assert set(body["accessible_departments"]) == {"finance", "general"}


def test_me_endpoint_reports_role(client: TestClient):
    _login(client, "hr.lead")
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == "hr"


def test_health_and_metrics_open(client: TestClient):
    assert client.get("/health").status_code == 200
    assert client.get("/metrics").status_code == 200
