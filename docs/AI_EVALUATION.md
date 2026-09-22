# Automated Golden Dataset Evaluation

## 1. Why Golden Benchmarks?

In production AI systems, prompt adjustments and code changes can cause silent behavioral regressions. Signal Market Bot ships with a native offline evaluation harness (`backend/evals/`) executing against a curated golden dataset.

---

## 2. Evaluation Metrics

For each test case, the harness evaluates:
- **Decision Adherence**: Did the agent correctly choose between `reply`, `draft_for_human`, `handoff`, etc.?
- **Skill Selection Precision**: Did the agent activate the exact required skill (e.g., `product-sales` or `complaints`)?
- **Governed Tool Verification**: Were sensitive tools properly blocked or safe tools executed?
- **Keyword Recall Grounding**: Does the response contain domain-specific grounding facts?
- **Latency & Tokens**: Execution duration in milliseconds and token footprint.

---

## 3. Running Evaluations

### Via CLI
```bash
cd backend
python evals/run_evals.py
```

### In Continuous Integration (CI)
The test suite runs automatically on every pull request and push in `.github/workflows/ci.yml`. A regression failing pass rate criteria halts CI and blocks deployment.

### In Admin Console (AI Studio)
Operators and administrators can trigger the evaluation suite live from **AI Studio > Evaluation Suite** to inspect real-time accuracy and latency benchmarks.
