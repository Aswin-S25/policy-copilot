"""Evaluation gates: compare a run against the stored baseline.

Two kinds of checks:
  regression  a metric may not drop more than its tolerance below baseline
  floor       a metric may never fall below an absolute target
Comparisons only make sense on the same dataset, so a baseline built on a
different number of cases fails the gate until it is regenerated.
"""
import json
from dataclasses import dataclass
from pathlib import Path

BASELINE_PATH = Path("eval/baseline.json")

# Maximum allowed drop vs baseline. Retrieval is deterministic, so its
# tolerance is tight; answer metrics come from an LLM and an LLM judge.
TOLERANCES = {
    ("retrieval", "recall_at_5"): 0.03,
    ("retrieval", "mrr"): 0.03,
    ("answers", "refusal_accuracy"): 0.03,
    ("answers", "faithfulness"): 0.03,
    ("answers", "relevance"): 0.05,
    ("answers", "citation_correctness"): 0.05,
}

# Absolute targets; also rendered as "targets" in reports.
FLOORS = {
    ("retrieval", "recall_at_5"): 0.85,
    ("retrieval", "mrr"): 0.70,
    ("answers", "refusal_accuracy"): 0.90,
    ("answers", "faithfulness"): 0.90,
    # Averages are only trusted if almost every case was answered and judged.
    ("answers", "answer_coverage"): 0.95,
    ("answers", "judge_coverage"): 0.95,
}

EPSILON = 1e-9


@dataclass
class Check:
    metric: str
    kind: str              # "dataset" | "regression" | "floor"
    baseline: float | int | None
    current: float | int | None
    limit: float | None
    passed: bool


def targets() -> dict:
    return {name: floor for (_, name), floor in FLOORS.items()}


def load_baseline_or_none() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def check_regressions(
    baseline: dict | None,
    current: dict,
    sections: tuple[str, ...] = ("retrieval", "answers"),
) -> list[Check]:
    checks = []

    if baseline is not None:
        baseline_cases = baseline.get("dataset", {}).get("cases")
        current_cases = current.get("dataset", {}).get("cases")
        same_dataset = baseline_cases == current_cases
        checks.append(Check(
            "dataset.cases", "dataset",
            baseline_cases, current_cases, None, same_dataset,
        ))

        if same_dataset:
            for (section, name), tolerance in TOLERANCES.items():
                if section not in sections:
                    continue
                old = baseline.get(section, {}).get(name)
                new = current.get(section, {}).get(name)
                if old is None or new is None:
                    continue
                checks.append(Check(
                    f"{section}.{name}", "regression",
                    old, new, tolerance, old - new <= tolerance + EPSILON,
                ))

    for (section, name), floor in FLOORS.items():
        if section not in sections:
            continue
        value = current.get(section, {}).get(name)
        if value is None:
            continue
        checks.append(Check(
            f"{section}.{name}", "floor",
            None, value, floor, value >= floor - EPSILON,
        ))

    return checks


def floor_checks_passed(checks: list[Check]) -> bool:
    return all(c.passed for c in checks if c.kind == "floor")


def print_checks(checks: list[Check]) -> bool:
    def fmt(value):
        if value is None:
            return "-"
        return f"{value:.4f}" if isinstance(value, float) else str(value)

    print()
    print(f"{'metric':<34}{'check':<12}{'baseline':>10}{'current':>10}{'limit':>10}  result")
    for c in checks:
        print(f"{c.metric:<34}{c.kind:<12}{fmt(c.baseline):>10}{fmt(c.current):>10}"
              f"{fmt(c.limit):>10}  {'PASS' if c.passed else 'FAIL'}")
    return all(c.passed for c in checks)
