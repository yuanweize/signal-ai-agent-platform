#!/usr/bin/env python3
"""
CLI Runner for the AI Golden Test Dataset Evaluation Suite.
Can be executed in local terminal or during CI pipeline:
    python evals/run_evals.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Explicitly ensure evaluation test runner executes under test environment
os.environ.setdefault("ENVIRONMENT", "test")

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.ai.evals.runner import EvaluationRunner  # noqa: E402
from app.ai.providers.llm import FakeLLMProvider  # noqa: E402
from app.ai.runtime.agent_runtime import AgentRuntime  # noqa: E402
from app.database import Base  # noqa: E402


async def main() -> int:
    print("=" * 70)
    print("  Deterministic Agent Contract Evaluation Suite (32 Invariants)")
    print("=" * 70)

    # In-memory test engine for isolated eval execution
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    dataset_path = backend_dir / "evals" / "datasets" / "golden_dataset.json"
    print(f"Loading golden dataset from: {dataset_path}")

    runner = EvaluationRunner(dataset_path=dataset_path)
    llm = FakeLLMProvider()
    runtime = AgentRuntime(llm_provider=llm)

    async with async_session() as session:
        summary = await runner.run_suite(session=session, runtime=runtime)

    print("\nBenchmark Results:")
    print(f"  Total Test Cases : {summary['total_cases']}")
    print(f"  Passed Cases     : {summary['passed_cases']}")
    print(f"  Pass Rate        : {summary['pass_rate'] * 100:.1f}%")
    print(f"  Decision Accuracy: {summary['decision_accuracy'] * 100:.1f}%")
    print(f"  Avg Latency      : {summary['average_latency_ms']} ms")
    print(f"  Total Tokens     : {summary['total_tokens']}")

    print("\nCase Breakdown:")
    print("-" * 70)
    print(f"{'Case ID':<16} | {'Status':<6} | {'Expected':<12} | {'Actual':<12} | {'Latency':<8}")
    print("-" * 70)
    for res in summary["results"]:
        status = "PASS" if res["passed"] else "FAIL"
        print(
            f"{res['case_id']:<16} | {status:<6} | {'match':<12} | "
            f"{res['actual_decision']:<12} | {res['latency_ms']}ms"
        )
    print("-" * 70)

    await engine.dispose()

    # Pass condition: all golden test cases executed with 100% decision match
    if summary["passed_cases"] == summary["total_cases"] and summary["total_cases"] > 0:
        print("\n✅ All AI Evaluation benchmarks PASSED successfully!\n")
        return 0
    else:
        print("\n❌ AI Evaluation benchmarks FAILED pass rate criteria!\n")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
