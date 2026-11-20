
from app.core.db import SessionLocal

from eval.lib.load import load_golden_cases
from eval.lib.retrieval import (
    evaluate_retrieval_case,
    calculate_metrics,
)


def run_comparison():
    cases = load_golden_cases()
    db = SessionLocal()

    strategies = ("dense", "lexical", "hybrid", "auto")

    try:
        results = {}

        for strategy in strategies:
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

            metrics = calculate_metrics(strategy_results)
            results[strategy] = metrics

        print()
        print("=" * 75)
        print("RETRIEVAL STRATEGY COMPARISON")
        print("=" * 75)

        print(
            f"{'Metric':<15}"
            + "".join(f"{s.upper():>14}" for s in strategies)
        )

        print("-" * 75)

        print(
            f"{'Recall@5':<15}"
            + "".join(
                f"{results[s].recall_at_5:>14.4f}"
                for s in strategies
            )
        )

        print(
            f"{'MRR':<15}"
            + "".join(
                f"{results[s].mrr:>14.4f}"
                for s in strategies
            )
        )

        return results

    finally:
        db.close()


if __name__ == "__main__":
    run_comparison()
