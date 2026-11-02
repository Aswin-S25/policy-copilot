from app.db import SessionLocal

from eval.load import load_golden_cases

from eval.retrieval import (
    evaluate_retrieval_case,
    calculate_metrics,
)


def run_comparison():

    cases = load_golden_cases()

    db = SessionLocal()

    try:
        results = {}

        for strategy in ("dense", "hybrid"):

            print()
            print(f"Running {strategy.upper()} retrieval")
            print("-" * 40)

            strategy_results = []

            for case in cases:

                result = evaluate_retrieval_case(
                    db=db,
                    case=case,
                    top_k=5,
                    strategy=strategy,
                )

                strategy_results.append(result)

            metrics = calculate_metrics(
                strategy_results
            )

            results[strategy] = metrics

        # Compare
        dense = results["dense"]
        hybrid = results["hybrid"]

        print()
        print("=" * 65)
        print("DENSE VS HYBRID RETRIEVAL")
        print("=" * 65)

        print(
            f"{'Metric':<20}"
            f"{'Dense':>12}"
            f"{'Hybrid':>12}"
            f"{'Change':>12}"
        )

        print("-" * 65)

        recall_change = (
            hybrid.recall_at_5 - dense.recall_at_5
        )

        mrr_change = (
            hybrid.mrr - dense.mrr
        )

        print(
            f"{'Recall@5':<20}"
            f"{dense.recall_at_5:>12.4f}"
            f"{hybrid.recall_at_5:>12.4f}"
            f"{recall_change:>+12.4f}"
        )

        print(
            f"{'MRR':<20}"
            f"{dense.mrr:>12.4f}"
            f"{hybrid.mrr:>12.4f}"
            f"{mrr_change:>+12.4f}"
        )

        return results

    finally:
        db.close()


if __name__ == "__main__":
    run_comparison()