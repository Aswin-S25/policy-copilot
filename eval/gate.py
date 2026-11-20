"""One command for the evaluation gates.

    python -m eval.gate          # fast tier: no LLM, minutes (every change)
    python -m eval.gate --full   # + answer quality and LLM security evals

Fast tier
  unit_tests             pytest against the test database
  retrieval_regression   hybrid Recall@5 / MRR on the golden set vs baseline
  security_retrieval     zero leaked chunks across all role sets
Full tier adds
  answer_regression      eval.pipeline: refusal accuracy, faithfulness,
                         relevance, citation correctness vs baseline
  security_answers       eval.security_eval --answers (fingerprint leaks)
  conversation_security  eval.conversation_security_eval

Exit status 1 if any stage fails. Summary: eval/reports/gate.json; each
stage's full output: eval/reports/gate_<stage>.log.
"""
import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from eval.provenance import provenance

REPORT_DIR = Path("eval/reports")


@dataclass
class StageResult:
    name: str
    passed: bool
    seconds: float
    detail: str


def run_module(name: str, args: list[str]) -> StageResult:
    start = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    output = proc.stdout + proc.stderr
    (REPORT_DIR / f"gate_{name}.log").write_text(output, encoding="utf-8")

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return StageResult(
        name=name,
        passed=proc.returncode == 0,
        seconds=round(time.perf_counter() - start, 1),
        detail=" | ".join(lines[-2:]),
    )


def retrieval_regression() -> StageResult:
    from app.db import SessionLocal
    from eval.load import load_golden_cases
    from eval.regression import check_regressions, load_baseline_or_none, print_checks
    from eval.retrieval import calculate_metrics, evaluate_retrieval_case

    start = time.perf_counter()
    cases = load_golden_cases()
    with SessionLocal() as db:
        results = [
            evaluate_retrieval_case(db=db, case=case, top_k=5, strategy="hybrid")
            for case in cases
        ]
    metrics = calculate_metrics(results)

    current = {
        "dataset": {"cases": len(cases)},
        "retrieval": {"recall_at_5": metrics.recall_at_5, "mrr": metrics.mrr},
    }
    baseline = load_baseline_or_none()
    checks = check_regressions(baseline, current, sections=("retrieval",))
    passed = print_checks(checks)

    failed = [f"{c.metric} ({c.kind})" for c in checks if not c.passed]
    detail = f"Recall@5={metrics.recall_at_5:.4f} MRR={metrics.mrr:.4f}"
    if baseline is None:
        detail += " (no baseline: floors only)"
    if failed:
        detail += " FAILED: " + ", ".join(failed)

    return StageResult("retrieval_regression", passed,
                       round(time.perf_counter() - start, 1), detail)


def main(full: bool) -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    stages = [
        lambda: run_module("unit_tests", ["-m", "pytest", "-q"]),
        retrieval_regression,
        lambda: run_module("security_retrieval", ["-m", "eval.security_eval"]),
    ]
    if full:
        stages += [
            lambda: run_module("answer_regression", ["-m", "eval.pipeline"]),
            lambda: run_module("security_answers", ["-m", "eval.security_eval", "--answers"]),
            lambda: run_module("conversation_security",
                               ["-m", "eval.conversation_security_eval"]),
        ]

    results = []
    for stage in stages:
        result = stage()
        results.append(result)
        print(f"[{'PASS' if result.passed else 'FAIL'}] {result.name:<22} "
              f"{result.seconds:>7.1f}s  {result.detail}", flush=True)

    passed = all(r.passed for r in results)
    report = {
        "tier": "full" if full else "fast",
        "passed": passed,
        "provenance": provenance(),
        "stages": [asdict(r) for r in results],
    }
    (REPORT_DIR / "gate.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nGATE ({report['tier']}): {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="include LLM-based stages")
    sys.exit(main(parser.parse_args().full))
