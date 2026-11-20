"""Compare every retrieval strategy on the golden set, overall and per category."""
import time
from collections import defaultdict

from app.core.db import SessionLocal
from eval.lib.load import load_golden_cases
from eval.lib.retrieval import (
    calculate_metrics,
    evaluate_retrieval_case,
    recall_at_k,
    reciprocal_rank,
)

STRATEGIES = [
    "dense", "lexical", "hybrid", "auto",
    "reranked", "diverse_2", "diverse_3",
]


def run_comparison():
    import json
    from pathlib import Path

    categories = {
        c["id"]: c.get("category", "unknown")
        for c in json.loads(Path("eval/datasets/golden.json").read_text(encoding="utf-8"))
    }
    cases = load_golden_cases()
    answerable = [c for c in cases if c.relevant_chunk_ids]

    db = SessionLocal()
    summary = {}
    try:
        for strategy in STRATEGIES:
            results, latencies = [], []
            for case in answerable:
                start = time.perf_counter()
                results.append(evaluate_retrieval_case(db=db, case=case, top_k=5, strategy=strategy))
                latencies.append((time.perf_counter() - start) * 1000)
                db.rollback()  # never leave the session idle in transaction

            by_cat = defaultdict(list)
            for r in results:
                by_cat[categories[r.case_id]].append(r)

            latencies.sort()
            summary[strategy] = {
                "overall": calculate_metrics(results),
                "zero_hit": sum(1 for r in results if reciprocal_rank(r) == 0),
                "p50_ms": latencies[len(latencies) // 2],
                "p95_ms": latencies[int(len(latencies) * 0.95) - 1],
                "by_cat": {
                    cat: (
                        sum(recall_at_k(r, 5) for r in rs) / len(rs),
                        sum(reciprocal_rank(r) for r in rs) / len(rs),
                        len(rs),
                    )
                    for cat, rs in by_cat.items()
                },
            }
            m = summary[strategy]
            print(f"{strategy:<10} R@5={m['overall'].recall_at_5:.4f} MRR={m['overall'].mrr:.4f}", flush=True)
    finally:
        db.close()

    print()
    print(f"Answerable cases: {len(answerable)}")
    print(f"{'Strategy':<11}{'Recall@5':>10}{'MRR':>8}{'Misses':>8}{'p50 ms':>9}{'p95 ms':>9}")
    for s, m in summary.items():
        print(f"{s:<11}{m['overall'].recall_at_5:>10.4f}{m['overall'].mrr:>8.4f}"
              f"{m['zero_hit']:>8}{m['p50_ms']:>9.1f}{m['p95_ms']:>9.1f}")

    cats = sorted({c for m in summary.values() for c in m["by_cat"]})
    print()
    print("Recall@5 by category")
    print(f"{'Category':<16}{'n':>4}" + "".join(f"{s:>11}" for s in STRATEGIES))
    for cat in cats:
        n = summary[STRATEGIES[0]]["by_cat"][cat][2]
        print(f"{cat:<16}{n:>4}" + "".join(f"{summary[s]['by_cat'][cat][0]:>11.3f}" for s in STRATEGIES))
    print()
    print("MRR by category")
    print(f"{'Category':<16}{'n':>4}" + "".join(f"{s:>11}" for s in STRATEGIES))
    for cat in cats:
        n = summary[STRATEGIES[0]]["by_cat"][cat][2]
        print(f"{cat:<16}{n:>4}" + "".join(f"{summary[s]['by_cat'][cat][1]:>11.3f}" for s in STRATEGIES))


if __name__ == "__main__":
    run_comparison()
