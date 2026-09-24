"""
Tests for Evaluation History Contract and Null Token Safety.
Verifies Section 4 & Section 22:
- EvaluationRunDTO contract exact fields: average_latency_ms, total_tokens: nullable, started_at, completed_at
- Evaluation run with total_tokens = None serializes properly
- Legacy missing measurements are returned as None, not fabricated into PASS/1.0
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_admin
from app.database import get_session
from app.main import app
from app.models.ai import EvaluationCaseResult, EvaluationRun
from app.schemas.auth import AdminUser


@pytest.mark.asyncio
async def test_evaluation_history_null_tokens_and_exact_fields(session):
    """Verify evaluation runs with null total_tokens serialize honestly with exact canonical fields."""
    now = datetime.now(UTC).replace(tzinfo=None)
    eval_run = EvaluationRun(
        eval_type="golden_dataset",
        status="completed",
        provider="openai_compatible",
        model="gpt-4o-mini",
        prompt_version="V1_CANONICAL",
        dataset_version="v0.4.1_golden",
        total_cases=10,
        passed_cases=9,
        pass_rate=0.9,
        decision_accuracy=0.9,
        avg_latency_ms=145.2,
        total_tokens=None,  # Nullable token measurement
        estimated_cost=None,
        started_at=now,
        completed_at=now,
    )
    case_result = EvaluationCaseResult(
        case_id="case_null_scores",
        status="PASS",
        expected_decision="reply",
        actual_decision="reply",
        latency_ms=120,
        tokens=None,
        details=None,  # Missing detail / unmeasured keyword_score & decision_correct
    )
    eval_run.case_results.append(case_result)
    session.add(eval_run)
    await session.commit()
    session.expire_all()

    app.dependency_overrides[get_current_admin] = lambda: AdminUser(username="test_admin")
    app.dependency_overrides[get_session] = lambda: session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/api/ai-studio/evals/runs")
            assert resp.status_code == 200, f"Failed: {resp.text}"
            runs = resp.json()
            assert len(runs) >= 1
            run_data = next(r for r in runs if r["id"] == eval_run.id)

            # Contract verification
            assert "average_latency_ms" in run_data
            assert run_data["average_latency_ms"] == 145.2
            assert "avg_latency_ms" not in run_data  # Stale field eliminated from DTO

            assert "started_at" in run_data
            assert run_data["started_at"] is not None
            assert "created_at" not in run_data  # Stale field eliminated from DTO

            assert "total_tokens" in run_data
            assert run_data["total_tokens"] is None  # Honest null, not converted to 0

            # Case level non-fabrication verification
            cases = run_data.get("results", [])
            assert len(cases) == 1
            case = cases[0]
            assert case["case_id"] == "case_null_scores"
            assert case["decision_correct"] is None  # Not fabricated as True/PASS
            assert case["keyword_score"] is None  # Not fabricated as 1.0
    finally:
        app.dependency_overrides.clear()
