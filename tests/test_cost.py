"""Cost computation and budget tracking."""

from __future__ import annotations

from app.monitoring.cost import build_usage, compute_cost, count_tokens


def test_token_counting_nonzero():
    assert count_tokens("hello world") > 0
    assert count_tokens("") == 0


def test_cost_computation_matches_rates(monkeypatch):
    # 1000 input + 1000 output tokens at default gpt-4o rates.
    cost = compute_cost(input_tokens=1000, output_tokens=1000, embedding_tokens=0)
    # 0.0025 + 0.010 = 0.0125
    assert abs(cost - 0.0125) < 1e-6


def test_build_usage_totals():
    usage = build_usage(100, 50, 20)
    assert usage.total_tokens == 170
    assert usage.cost_usd >= 0
