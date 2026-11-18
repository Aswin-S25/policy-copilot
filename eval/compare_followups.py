"""Conversations step 2 measurement: does rewriting follow-ups into
standalone questions improve retrieval?

Turn 1 is a golden question answered by the real pipeline. The follow-up's
ground truth is the relevant chunks of a target golden case. Retrieval
(search_policies, all roles) is compared for:
  raw      the follow-up as typed
  concat   previous question + follow-up (cheap baseline, no LLM)
  rewrite  LLM standalone rewrite (app/followup.py)
  oracle   the target golden question (upper bound)

    python -m eval.compare_followups
    python -m eval.compare_followups --fresh   # regenerate rewrites
"""
import argparse
import json
import os
from pathlib import Path

from ollama import Client

import app.llm
from app.authz import ALL_ROLES
from app.db import SessionLocal
from app.followup import HistoryTurn, rewrite_question
from app.rag import answer_question
from app.search import search_policies
from eval.load import load_golden_cases

CASES_PATH = Path("eval/followups.json")
CACHE_PATH = Path("eval/reports/followup_cache.json")
REPORT_PATH = Path("eval/reports/followup_comparison.json")
VARIANTS = ["raw", "concat", "rewrite", "oracle"]

OLLAMA_TIMEOUT_S = int(os.environ.get("OLLAMA_TIMEOUT_S", "300"))
app.llm.client = Client(host=app.llm.OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_S)


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else float("nan")


def scores(chunks, relevant):
    ids = [str(c.chunk_id) for c in chunks]
    recall = len(set(ids) & relevant) / len(relevant)
    rr = next((1 / i for i, cid in enumerate(ids, 1) if cid in relevant), 0.0)
    return recall, rr


def save(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def main(fresh: bool):
    golden = {c.id: c for c in load_golden_cases()}
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    cache = (json.loads(CACHE_PATH.read_text(encoding="utf-8"))
             if CACHE_PATH.exists() else {"turn1": {}, "rewrite": {}})
    if fresh:
        cache["rewrite"] = {}

    rows = []
    db = SessionLocal()
    try:
        for case in cases:
            prior = golden[case["history"]]
            target = golden[case["target"]]

            if prior.id not in cache["turn1"]:
                cache["turn1"][prior.id] = answer_question(
                    db=db, question=prior.question, roles=ALL_ROLES
                ).answer
                save(cache)
                print(f"  answered turn 1: {prior.id}", flush=True)

            history = [
                HistoryTurn("user", prior.question),
                HistoryTurn("assistant", cache["turn1"][prior.id]),
            ]

            key = f"{case['id']}|{case['question']}"
            if key not in cache["rewrite"]:
                cache["rewrite"][key] = rewrite_question(history, case["question"])
                save(cache)
            rewritten = cache["rewrite"][key]

            queries = {
                "raw": case["question"],
                "concat": f"{prior.question} {case['question']}",
                "rewrite": rewritten,
                "oracle": target.question,
            }
            result = {
                variant: scores(
                    search_policies(db=db, query=query, roles=ALL_ROLES),
                    target.relevant_chunk_ids,
                )
                for variant, query in queries.items()
            }
            rows.append({"case": case, "rewritten": rewritten, "scores": result})
            db.rollback()
    finally:
        db.close()

    groups = {
        "followup": [r for r in rows if r["case"]["type"] == "followup"],
        "switch": [r for r in rows if r["case"]["type"] == "switch"],
        "all": rows,
    }

    report = {}
    for metric, idx in (("Recall@5", 0), ("MRR", 1)):
        print(f"\n{metric}")
        print("-" * len(metric))
        print(f"{'':<16}" + "".join(f"{v:>10}" for v in VARIANTS))
        for name, group in groups.items():
            values = [mean(r["scores"][v][idx] for r in group) for v in VARIANTS]
            report.setdefault(name, {})[metric] = dict(zip(VARIANTS, values))
            print(f"{name + f' (n={len(group)})':<16}" + "".join(f"{x:>10.3f}" for x in values))

    print("\nPer case (Recall@5 raw -> rewrite | oracle):")
    for r in rows:
        s = r["scores"]
        print(f"  {r['case']['id']:<7} {r['case']['type']:<8} "
              f"{s['raw'][0]:.2f} -> {s['rewrite'][0]:.2f} | {s['oracle'][0]:.2f}  "
              f"{r['case']['question']!r} => {r['rewritten']!r}")

    report["cases"] = [
        {"id": r["case"]["id"], "rewritten": r["rewritten"],
         "scores": {v: {"recall_at_5": s[0], "mrr": s[1]} for v, s in r["scores"].items()}}
        for r in rows
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved {REPORT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true", help="regenerate rewrites")
    main(parser.parse_args().fresh)
