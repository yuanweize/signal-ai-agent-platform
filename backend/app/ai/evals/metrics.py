"""
Evaluation metrics for agent grounding, decision adherence, and safety.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CaseEvalResult:
    """Evaluation score and diagnostic details for a single golden case."""

    case_id: str
    case_name: str
    decision_correct: bool
    skill_correct: bool
    tool_correct: bool
    keyword_score: float
    overall_passed: bool
    actual_decision: str
    actual_answer: str
    latency_ms: int
    tokens: int
    notes: str = ""


def evaluate_case_result(case: dict[str, Any], response: Any) -> CaseEvalResult:
    """Evaluate response against expected golden case expectations."""
    expected_dec = case.get("expected_decision")
    decision_correct = (response.decision == expected_dec) if expected_dec else True

    expected_skill = case.get("expected_skill")
    skill_correct = (expected_skill in response.skills_used) if expected_skill else True

    expected_tool = case.get("expected_tool")
    tool_names = [t.get("name") for t in response.tools_called]
    tool_correct = (expected_tool in tool_names) if expected_tool else True

    expected_kw = case.get("expected_keywords", [])
    ans_lower = response.answer.lower()
    if expected_kw:
        matched = sum(1 for kw in expected_kw if kw.lower() in ans_lower)
        keyword_score = matched / len(expected_kw)
    else:
        keyword_score = 1.0

    passed = decision_correct and skill_correct and tool_correct and (keyword_score >= 0.3)

    return CaseEvalResult(
        case_id=case["id"],
        case_name=case.get("name", case["id"]),
        decision_correct=decision_correct,
        skill_correct=skill_correct,
        tool_correct=tool_correct,
        keyword_score=round(keyword_score, 2),
        overall_passed=passed,
        actual_decision=response.decision,
        actual_answer=response.answer,
        latency_ms=response.latency_ms,
        tokens=response.tokens,
    )
