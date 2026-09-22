"""
Automated AI evaluation suite runner.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evals.metrics import CaseEvalResult, evaluate_case_result
from app.ai.runtime.agent_runtime import AgentRuntime
from app.ai.runtime.context import AgentContext

logger = logging.getLogger("ai.evals.runner")


class EvaluationRunner:
    """Executes evaluation benchmarks against the golden test dataset."""

    def __init__(self, dataset_path: Path | None = None) -> None:
        if dataset_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.dataset_path = base_dir / "evals" / "datasets" / "golden_dataset.json"
        else:
            self.dataset_path = Path(dataset_path)

    def load_dataset(self) -> list[dict[str, Any]]:
        if not self.dataset_path.exists():
            logger.error(f"Evaluation dataset not found at {self.dataset_path}")
            return []
        return json.loads(self.dataset_path.read_text(encoding="utf-8"))

    async def run_suite(
        self,
        session: AsyncSession,
        runtime: AgentRuntime,
    ) -> dict[str, Any]:
        """Run all golden test cases and aggregate metrics."""
        cases = self.load_dataset()
        results: list[CaseEvalResult] = []

        for idx, case in enumerate(cases):
            ctx_data = case.get("context", {})
            context = AgentContext(
                conversation_id=9000 + idx,
                message_id=8000 + idx,
                sender_id="+420777111222",
                text=case["input"],
                is_group=ctx_data.get("is_group", False),
                mode=ctx_data.get("mode", "auto"),
            )
            response = await runtime.run(session=session, context=context)
            eval_res = evaluate_case_result(case, response)
            results.append(eval_res)

        total = len(results)
        passed = sum(1 for r in results if r.overall_passed)
        dec_correct = sum(1 for r in results if r.decision_correct)
        avg_latency = sum(r.latency_ms for r in results) / total if total > 0 else 0
        total_tokens = sum(r.tokens for r in results)

        summary = {
            "total_cases": total,
            "passed_cases": passed,
            "pass_rate": round(passed / total, 2) if total > 0 else 0.0,
            "decision_accuracy": round(dec_correct / total, 2) if total > 0 else 0.0,
            "average_latency_ms": round(avg_latency, 1),
            "total_tokens": total_tokens,
            "results": [
                {
                    "case_id": r.case_id,
                    "case_name": r.case_name,
                    "passed": r.overall_passed,
                    "decision_correct": r.decision_correct,
                    "actual_decision": r.actual_decision,
                    "keyword_score": r.keyword_score,
                    "latency_ms": r.latency_ms,
                    "tokens": r.tokens,
                }
                for r in results
            ],
        }
        return summary


eval_runner = EvaluationRunner()
