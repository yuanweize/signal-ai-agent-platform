"""
Automated AI evaluation suite runner.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evals.metrics import CaseEvalResult, evaluate_case_result
from app.ai.prompts.manager import prompt_manager
from app.ai.runtime.agent_runtime import AgentRuntime
from app.ai.runtime.context import AgentContext
from app.models.ai import EvaluationCaseResult, EvaluationRun
from app.services.sandbox import get_or_create_sandbox_conversation

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
        limit: int | None = None,
        eval_type: str = "deterministic",
    ) -> dict[str, Any]:
        """Run golden test cases, isolate eval traffic, and persist evaluation run history."""
        started_at = datetime.now(UTC).replace(tzinfo=None)
        cases = self.load_dataset()
        if limit is not None and limit > 0:
            cases = cases[:limit]

        results: list[CaseEvalResult] = []

        model_name = getattr(runtime.llm_provider, "default_model", "unknown")
        provider_name = getattr(runtime.llm_provider, "provider_name", "unknown")

        # Resolve active prompt version
        try:
            active_version, _ = await prompt_manager.get_active_prompt(session)
        except Exception:
            active_version = "v1.0"

        # Dedicated sandbox conversation ensures no customer conversation contamination and no FK violations
        sandbox_conv_id = await get_or_create_sandbox_conversation(
            session, "__system_eval_sandbox__"
        )

        for idx, case in enumerate(cases):
            ctx_data = case.get("context", {})
            # Isolate evaluation traffic: message_id=None avoids duplicate suppression on repeat runs
            context = AgentContext(
                conversation_id=sandbox_conv_id,
                message_id=None,
                sender_id="+420777111222",
                text=case["input"],
                is_group=ctx_data.get("is_group", False),
                mode=ctx_data.get("mode", "auto"),
                traffic_source="evaluation",
            )
            response = await runtime.run(session=session, context=context)
            eval_res = evaluate_case_result(case, response)
            results.append(eval_res)

        total = len(results)
        passed = sum(1 for r in results if r.overall_passed)
        dec_correct = sum(1 for r in results if r.decision_correct)
        avg_latency = sum(r.latency_ms for r in results) / total if total > 0 else 0

        # Truthful token semantics: if no calls returned usage, total_tokens is None (not fabricated 0)
        has_tokens = any(r.tokens is not None and r.tokens > 0 for r in results)
        total_tokens_val = (
            sum(r.tokens for r in results if r.tokens is not None) if has_tokens else None
        )
        completed_at = datetime.now(UTC).replace(tzinfo=None)

        case_results_list = [
            {
                "case_id": r.case_id,
                "case_name": r.case_name,
                "passed": r.overall_passed,
                "decision_correct": r.decision_correct,
                "expected_decision": case.get("expected", {}).get("decision") or "",
                "actual_decision": r.actual_decision,
                "keyword_score": r.keyword_score,
                "latency_ms": r.latency_ms,
                "tokens": r.tokens,
            }
            for r, case in zip(results, cases, strict=False)
        ]

        # Persist EvaluationRun record with real prompt version and nullable tokens
        eval_run = EvaluationRun(
            eval_type=eval_type,
            provider=provider_name,
            model=model_name,
            prompt_version=active_version,
            dataset_version="golden_v1",
            total_cases=total,
            passed_cases=passed,
            pass_rate=round(passed / total, 2) if total > 0 else 0.0,
            decision_accuracy=round(dec_correct / total, 2) if total > 0 else 0.0,
            avg_latency_ms=round(avg_latency, 1),
            total_tokens=total_tokens_val,
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
        )
        session.add(eval_run)
        await session.flush()

        for r, case in zip(results, cases, strict=False):
            cr = EvaluationCaseResult(
                run_id=eval_run.id,
                case_id=r.case_id,
                status="PASS" if r.overall_passed else "FAIL",
                expected_decision=case.get("expected", {}).get("decision") or "",
                actual_decision=r.actual_decision,
                latency_ms=r.latency_ms,
                tokens=r.tokens,
                details=json.dumps(
                    {
                        "case_name": r.case_name,
                        "decision_correct": r.decision_correct,
                        "keyword_score": r.keyword_score,
                    }
                ),
            )
            session.add(cr)

        await session.commit()
        await session.refresh(eval_run)

        summary = {
            "run_id": eval_run.id,
            "eval_type": eval_type,
            "total_cases": total,
            "passed_cases": passed,
            "pass_rate": eval_run.pass_rate,
            "decision_accuracy": eval_run.decision_accuracy,
            "average_latency_ms": eval_run.avg_latency_ms,
            "total_tokens": total_tokens_val,
            "results": case_results_list,
        }
        return summary


eval_runner = EvaluationRunner()
