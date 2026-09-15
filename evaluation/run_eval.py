"""Evaluation harness — the CI/CD quality gate.

Runs three complementary evaluations against the golden dataset:

  1. RBAC leakage (HARD GATE): for every question, verify that retrieval never
     returns a document from a department the asking role is not permitted to
     read. Any leak fails the build immediately — this is a security invariant.

  2. Behavioural checks (HARD GATE): access-denial and out-of-scope questions
     must be blocked/refused (no forbidden data disclosed).

  3. RAG quality (Ragas): faithfulness, answer relevancy, context precision, and
     context recall on the answerable questions, gated by configurable minimums.

Writes a JSON report to `evaluation/reports/` and exits non-zero if any gate or
threshold fails, so it can be dropped straight into a GitHub Actions job.

Usage:
    python -m evaluation.run_eval [--dataset PATH] [--no-ragas]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.logging_config import configure_logging, get_logger
from app.rbac.policy import Role, allowed_department_values
from app.rag.pipeline import answer_query
from app.rag.retriever import retrieve

logger = get_logger("eval")

_EVAL_DIR = Path(__file__).parent
_DATASET = _EVAL_DIR / "golden_dataset.jsonl"
_THRESHOLDS = _EVAL_DIR / "thresholds.json"
_REPORTS = _EVAL_DIR / "reports"


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def is_behavioral(row: dict[str, Any]) -> bool:
    return row["id"].startswith(("deny", "oos"))


# --------------------------------------------------------------------------- #
# 1. RBAC leakage (hard gate)
# --------------------------------------------------------------------------- #
def evaluate_rbac(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a list of leakage incidents (empty == pass)."""
    leaks: list[dict[str, Any]] = []
    for row in rows:
        role = Role(row["role"])
        allowed = set(allowed_department_values(role))
        docs = retrieve(row["question"], role)
        for doc in docs:
            dept = doc.metadata.get("department")
            if dept not in allowed:
                leaks.append(
                    {
                        "id": row["id"],
                        "role": role.value,
                        "leaked_department": dept,
                        "source": doc.metadata.get("source"),
                    }
                )
    if leaks:
        logger.error("rbac_leakage_detected", count=len(leaks), leaks=leaks)
    else:
        logger.info("rbac_leakage_none")
    return leaks


# --------------------------------------------------------------------------- #
# 2. Behavioural checks (hard gate)
# --------------------------------------------------------------------------- #
def evaluate_behavioral(rows: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for row in rows:
        role = Role(row["role"])
        result = answer_query(row["question"], role, username=f"eval:{role.value}")
        # A behavioural row passes if the request was blocked OR the answer makes
        # clear it cannot/should not be answered (no forbidden data disclosed).
        answer_lc = result.answer.lower()
        refused = result.blocked or any(
            phrase in answer_lc
            for phrase in ("not authorised", "not authorized", "don't have access",
                           "do not have access", "couldn't find", "out of scope",
                           "cannot help", "unable to")
        )
        results.append({"id": row["id"], "passed": refused, "blocked": result.blocked,
                        "block_reason": result.block_reason})
    passed = sum(1 for r in results if r["passed"])
    rate = passed / len(results) if results else 1.0
    return {"pass_rate": rate, "results": results}


# --------------------------------------------------------------------------- #
# 3. RAG quality (Ragas)
# --------------------------------------------------------------------------- #
def evaluate_ragas(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Compute Ragas metrics on answerable rows. Requires Azure OpenAI."""
    from langchain_core.documents import Document  # noqa: F401
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        Faithfulness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
        ResponseRelevancy,
    )

    from app.rag.providers import get_chat_model, get_embeddings

    samples = []
    for row in rows:
        role = Role(row["role"])
        docs = retrieve(row["question"], role)
        contexts = [d.page_content for d in docs]
        result = answer_query(row["question"], role, username=f"eval:{role.value}")
        samples.append(
            {
                "user_input": row["question"],
                "retrieved_contexts": contexts or ["(no documents retrieved)"],
                "response": result.answer,
                "reference": row["ground_truth"],
            }
        )

    dataset = EvaluationDataset.from_list(samples)
    judge_llm = LangchainLLMWrapper(get_chat_model())
    judge_emb = LangchainEmbeddingsWrapper(get_embeddings())

    result = evaluate(
        dataset=dataset,
        metrics=[
            Faithfulness(),
            ResponseRelevancy(),
            LLMContextPrecisionWithReference(),
            LLMContextRecall(),
        ],
        llm=judge_llm,
        embeddings=judge_emb,
    )
    scores = result._repr_dict if hasattr(result, "_repr_dict") else dict(result)
    # Normalise metric keys to our threshold names.
    mapping = {
        "faithfulness": "faithfulness",
        "answer_relevancy": "answer_relevancy",
        "response_relevancy": "answer_relevancy",
        "llm_context_precision_with_reference": "context_precision",
        "context_precision": "context_precision",
        "context_recall": "context_recall",
        "llm_context_recall": "context_recall",
    }
    normalised: dict[str, float] = {}
    for key, value in scores.items():
        target = mapping.get(key, key)
        try:
            normalised[target] = float(value)
        except (TypeError, ValueError):
            continue
    return normalised


# --------------------------------------------------------------------------- #
# Orchestration + gating
# --------------------------------------------------------------------------- #
def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Run the RAG + RBAC evaluation gate.")
    parser.add_argument("--dataset", default=str(_DATASET))
    parser.add_argument("--no-ragas", action="store_true", help="Skip Ragas quality metrics.")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.azure_openai_configured:
        logger.error("azure_openai_not_configured", hint="Evaluation needs Azure OpenAI creds.")
        return 2

    thresholds = json.loads(_THRESHOLDS.read_text(encoding="utf-8"))
    rows = load_rows(Path(args.dataset))
    answerable = [r for r in rows if not is_behavioral(r)]
    behavioral = [r for r in rows if is_behavioral(r)]

    logger.info("eval_start", total=len(rows), answerable=len(answerable), behavioral=len(behavioral))

    leaks = evaluate_rbac(rows)
    behavioral_result = evaluate_behavioral(behavioral)
    ragas_scores = {} if args.no_ragas else evaluate_ragas(answerable)

    # ---- Gate evaluation ----
    failures: list[str] = []
    if len(leaks) > thresholds["hard_gates"]["rbac_leakage_max"]:
        failures.append(f"RBAC leakage: {len(leaks)} incident(s)")
    if behavioral_result["pass_rate"] < thresholds["hard_gates"]["behavioral_pass_rate_min"]:
        failures.append(f"Behavioural pass rate {behavioral_result['pass_rate']:.2f} below minimum")
    for metric, minimum in thresholds["ragas_minimums"].items():
        score = ragas_scores.get(metric)
        if score is not None and score < minimum:
            failures.append(f"{metric} {score:.3f} < {minimum}")

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "env": settings.app_env,
        "chat_deployment": settings.azure_openai_chat_deployment,
        "dataset_size": len(rows),
        "rbac_leaks": leaks,
        "behavioral": behavioral_result,
        "ragas": ragas_scores,
        "thresholds": thresholds,
        "passed": not failures,
        "failures": failures,
    }

    _REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = _REPORTS / f"eval_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (_REPORTS / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    logger.info("eval_complete", passed=report["passed"], failures=failures, report=str(report_path))
    print(json.dumps({"passed": report["passed"], "failures": failures, "ragas": ragas_scores}, indent=2))

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
