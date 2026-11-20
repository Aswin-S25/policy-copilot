from app.core.db import SessionLocal
from eval.lib.load import load_golden_cases
from eval.lib.retrieval import (
    calculate_metrics,
    evaluate_retrieval_case,
)


def run_strategy(db, cases, strategy):
    results = []

    for case in cases:
        result = evaluate_retrieval_case(
            db=db,
            case=case,
            top_k=5,
            strategy=strategy,
        )

        results.append(result)

    return calculate_metrics(results)


def run_comparison():
    cases = load_golden_cases()

    db = SessionLocal()

    try:
        print("Running DENSE retrieval")
        print("-" * 40)

        dense = run_strategy(
            db,
            cases,
            "dense",
        )

        print("Running HYBRID retrieval")
        print("-" * 40)

        hybrid = run_strategy(
            db,
            cases,
            "hybrid",
        )

        print("Running RERANKED retrieval")
        print("-" * 40)

        reranked = run_strategy(
            db,
            cases,
            "reranked",
        )

        print()
        print("=" * 70)
        print("DENSE VS HYBRID VS RERANKED")
        print("=" * 70)

        print(
            f"{'Metric':<20}"
            f"{'Dense':>12}"
            f"{'Hybrid':>12}"
            f"{'Reranked':>12}"
        )

        print("-" * 70)

        print(
            f"{'Recall@5':<20}"
            f"{dense.recall_at_5:>12.4f}"
            f"{hybrid.recall_at_5:>12.4f}"
            f"{reranked.recall_at_5:>12.4f}"
        )

        print(
            f"{'MRR':<20}"
            f"{dense.mrr:>12.4f}"
            f"{hybrid.mrr:>12.4f}"
            f"{reranked.mrr:>12.4f}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    run_comparison()