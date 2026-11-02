import json
from pathlib import Path
from datetime import datetime, timezone


def build_regression_section(
    results: dict,
    baseline_path: Path,
) -> str:

    regression = results.get("regression")

    if regression is None:
        return ""

    if not baseline_path.exists():
        return (
            "## Regression vs Baseline\n\n"
            "No baseline found; this run is the first baseline.\n"
        )

    baseline = json.loads(
        baseline_path.read_text(
            encoding="utf-8"
        )
    )

    baseline_recall = baseline["retrieval"]["recall_at_5"]
    current_recall = results["retrieval"]["recall_at_5"]
    drop = baseline_recall - current_recall
    status = "PASS" if regression["passed"] else "FAIL"

    return f"""## Regression vs Baseline

Baseline: {baseline.get("timestamp", "unknown")}

| Metric | Baseline | Current | Drop | Allowed Drop | Status |
|---|---:|---:|---:|---:|---|
| Recall@5 | {baseline_recall:.4f} | {current_recall:.4f} | {drop:.4f} | {regression["recall_drop_threshold"]:.4f} | {status} |
"""


def generate_report(
    results_path: str = "eval/reports/latest.json",
    output_path: str = "eval/reports/latest.md",
    baseline_path: str = "eval/baseline.json",
) -> Path:

    results = json.loads(
        Path(results_path).read_text(
            encoding="utf-8"
        )
    )

    output = Path(output_path)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    retrieval = results["retrieval"]
    answers = results["answers"]
    dataset = results["dataset"]
    targets = results["targets"]

    def status(actual, target):
        return "PASS" if actual >= target else "FAIL"

    regression_section = build_regression_section(
        results,
        Path(baseline_path),
    )

    report = f"""# Policy Copilot — Evaluation

Run: {results.get("timestamp", "unknown")}
Generated: {datetime.now(timezone.utc).isoformat()}

## Dataset

- Total cases: {dataset["cases"]}
- Answerable cases: {dataset["answerable_cases"]}
- Unanswerable cases: {dataset["unanswerable_cases"]}

## Retrieval

| Metric | Result | Target | Status |
|---|---:|---:|---|
| Recall@5 | {retrieval["recall_at_5"]:.4f} | {targets["recall_at_5"]:.2f} | {status(retrieval["recall_at_5"], targets["recall_at_5"])} |
| MRR | {retrieval["mrr"]:.4f} | {targets["mrr"]:.2f} | {status(retrieval["mrr"], targets["mrr"])} |

## Answer Quality

| Metric | Result | Target | Status |
|---|---:|---:|---|
| Faithfulness | {answers["faithfulness"]:.4f} | {targets["faithfulness"]:.2f} | {status(answers["faithfulness"], targets["faithfulness"])} |
| Refusal Accuracy | {answers["refusal_accuracy"]:.4f} | {targets["refusal_accuracy"]:.2f} | {status(answers["refusal_accuracy"], targets["refusal_accuracy"])} |
| Relevance | {answers["relevance"]:.4f} | — | — |
| Citation Correctness | {answers["citation_correctness"]:.4f} | — | — |

{regression_section}
## Judge Calibration

The answer-quality judge was calibrated against manually labeled examples.

Current judge classification accuracy:

**0.95**

This is considered sufficient for experimental automated evaluation, but
judge outputs should still be periodically audited against human labels.

## Current Architecture

```text
Query
  ↓
Dense Retrieval
  ↓
Context Budgeting
  ↓
Grounded Prompt
  ↓
Qwen3:8B
  ↓
Citation Validation
  ↓
Answer
  ↓
Qwen3:8B Judge
  ↓
Faithfulness / Relevance / Citation Correctness
```
"""

    output.write_text(
        report,
        encoding="utf-8",
    )

    return output


if __name__ == "__main__":
    print(f"Saved report → {generate_report()}")