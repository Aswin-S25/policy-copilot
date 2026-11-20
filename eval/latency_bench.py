"""Latency benchmark: per-stage percentiles over many questions.

Runs the real pipeline in-process, one request at a time, so the numbers are
service time without queueing (eval/load_probe.py covers queueing):
  single    golden questions through answer_question
  followup  rewrite + retrieval + generation, with the first turn's real
            answer as history (no conversation rows are written)
The model is warmed up first and one warm-up request is discarded.

    python -m eval.latency_bench
    python -m eval.latency_bench --single 60 --followups 20
"""
import argparse
import json
import math
import statistics
import time
from pathlib import Path

from app.authz import ALL_ROLES
from app.db import SessionLocal
from app.followup import HistoryTurn, rewrite_question
from app.llm import load_model
from app.observability import request_context
from app.rag import answer_from_chunks, answer_question
from app.search import search_policies
from eval.load import load_golden_cases
from eval.provenance import provenance

REPORT_PATH = Path("eval/reports/latency.json")
FOLLOWUPS_PATH = Path("eval/followups.json")
FOLLOWUP_CACHE = Path("eval/reports/followup_cache.json")
STAGES = ["total_ms", "rewrite_ms", "retrieval_ms", "llm_queue_ms", "generation_ms"]


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile."""
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def spread(items: list, n: int) -> list:
    """Deterministic sample spread evenly across the list."""
    if n >= len(items):
        return list(items)
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def measure(fn) -> dict:
    with request_context("latency-bench") as ctx:
        start = time.perf_counter()
        fn()
        total_ms = round((time.perf_counter() - start) * 1000, 1)
    row = {"total_ms": total_ms, **ctx["stages"]}
    row.update({k: ctx["fields"][k] for k in ("answer_outcome", "rewrite") if k in ctx["fields"]})
    return row


def summarize(rows: list[dict]) -> dict:
    summary = {}
    for stage in STAGES:
        values = [r[stage] for r in rows if stage in r]
        if values:
            summary[stage] = {
                "n": len(values),
                "p50": percentile(values, 50),
                "p95": percentile(values, 95),
                "max": max(values),
                "mean": round(statistics.mean(values), 1),
            }
    return summary


def print_summary(title: str, summary: dict) -> None:
    print(f"\n{title}")
    print(f"{'stage':<16}{'n':>5}{'p50':>10}{'p95':>10}{'max':>10}{'mean':>10}")
    for stage, s in summary.items():
        print(f"{stage:<16}{s['n']:>5}{s['p50']:>10.0f}{s['p95']:>10.0f}"
              f"{s['max']:>10.0f}{s['mean']:>10.0f}")


def main(n_single: int, n_followups: int) -> None:
    golden = load_golden_cases()
    by_id = {c.id: c for c in golden}
    followups = spread(json.loads(FOLLOWUPS_PATH.read_text(encoding="utf-8")), n_followups)
    turn1_cache = (
        json.loads(FOLLOWUP_CACHE.read_text(encoding="utf-8")).get("turn1", {})
        if FOLLOWUP_CACHE.exists() else {}
    )

    load_model()
    with SessionLocal() as db:
        answer_question(db=db, question=golden[0].question, roles=ALL_ROLES)  # discarded

        single_rows = []
        for i, case in enumerate(spread(golden, n_single), 1):
            row = measure(lambda: answer_question(db=db, question=case.question, roles=ALL_ROLES))
            row["case"] = case.id
            single_rows.append(row)
            db.rollback()
            print(f"  single {i}/{n_single} {case.id:<14} {row['total_ms']:>8.0f} ms", flush=True)

        followup_rows = []
        for i, fu in enumerate(followups, 1):
            prior = by_id[fu["history"]]
            first_answer = turn1_cache.get(prior.id) or answer_question(
                db=db, question=prior.question, roles=ALL_ROLES
            ).answer
            history = [HistoryTurn("user", prior.question),
                       HistoryTurn("assistant", first_answer)]

            def turn():
                standalone = rewrite_question(history, fu["question"])
                retrieved = search_policies(db=db, query=standalone, roles=ALL_ROLES)
                answer_from_chunks(question=standalone, retrieved=retrieved)

            row = measure(turn)
            row["case"] = fu["id"]
            followup_rows.append(row)
            db.rollback()
            print(f"  followup {i}/{len(followups)} {fu['id']:<8} {row['total_ms']:>8.0f} ms",
                  flush=True)

    report = {
        "provenance": provenance(),
        "mode": "sequential, in-process, warm model",
        "single": {"summary": summarize(single_rows), "rows": single_rows},
        "followup": {"summary": summarize(followup_rows), "rows": followup_rows},
    }
    print_summary(f"Single-turn (n={len(single_rows)}), ms", report["single"]["summary"])
    print_summary(f"Follow-up (n={len(followup_rows)}), ms", report["followup"]["summary"])

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved {REPORT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--single", type=int, default=30)
    parser.add_argument("--followups", type=int, default=20)
    args = parser.parse_args()
    main(args.single, args.followups)
