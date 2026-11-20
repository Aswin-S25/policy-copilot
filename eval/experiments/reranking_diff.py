from app.core.db import SessionLocal
from eval.lib.load import load_golden_cases
from eval.lib.retrieval import (
    evaluate_retrieval_case,
    recall_at_k,
)


def run_diff():
    cases = load_golden_cases()

    db = SessionLocal()

    try:
        improved = []
        degraded = []
        unchanged = []

        for case in cases:

            hybrid = evaluate_retrieval_case(
                db=db,
                case=case,
                top_k=5,
                strategy="hybrid",
            )

            reranked = evaluate_retrieval_case(
                db=db,
                case=case,
                top_k=5,
                strategy="reranked",
            )

            hybrid_recall = recall_at_k(
                hybrid,
                5,
            )

            reranked_recall = recall_at_k(
                reranked,
                5,
            )

            if reranked_recall > hybrid_recall:
                improved.append(
                    (case, hybrid, reranked)
                )

            elif reranked_recall < hybrid_recall:
                degraded.append(
                    (case, hybrid, reranked)
                )

            else:
                unchanged.append(case)

        print()
        print("=" * 70)
        print("HYBRID VS RERANKED")
        print("=" * 70)

        print(f"Improved : {len(improved)}")
        print(f"Degraded : {len(degraded)}")
        print(f"Unchanged: {len(unchanged)}")

        print()
        print("=" * 70)
        print("CASES IMPROVED BY RERANKING")
        print("=" * 70)

        for case, hybrid, reranked in improved:
            print()
            print(case.id)
            print(case.question)

            print()
            print("Relevant:")
            print(sorted(case.relevant_chunk_ids))

            print()
            print("Hybrid:")
            print(hybrid.retrieved_chunk_ids)

            print()
            print("Reranked:")
            print(reranked.retrieved_chunk_ids)

        print()
        print("=" * 70)
        print("CASES DEGRADED BY RERANKING")
        print("=" * 70)

        for case, hybrid, reranked in degraded:
            print()
            print(case.id)
            print(case.question)

            print()
            print("Relevant:")
            print(sorted(case.relevant_chunk_ids))

            print()
            print("Hybrid:")
            print(hybrid.retrieved_chunk_ids)

            print()
            print("Reranked:")
            print(reranked.retrieved_chunk_ids)

    finally:
        db.close()


if __name__ == "__main__":
    run_diff()