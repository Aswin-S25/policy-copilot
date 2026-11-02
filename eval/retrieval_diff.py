from app.db import SessionLocal

from eval.load import load_golden_cases
from eval.retrieval import (
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

            dense = evaluate_retrieval_case(
                db=db,
                case=case,
                top_k=5,
                strategy="dense",
            )

            hybrid = evaluate_retrieval_case(
                db=db,
                case=case,
                top_k=5,
                strategy="hybrid",
            )

            dense_recall = recall_at_k(
                dense,
                5,
            )

            hybrid_recall = recall_at_k(
                hybrid,
                5,
            )

            if hybrid_recall > dense_recall:

                improved.append(
                    (
                        case,
                        dense,
                        hybrid,
                    )
                )

            elif hybrid_recall < dense_recall:

                degraded.append(
                    (
                        case,
                        dense,
                        hybrid,
                    )
                )

            else:

                unchanged.append(case)

        print()
        print("=" * 70)
        print("RETRIEVAL DIFF")
        print("=" * 70)

        print(
            f"Improved : {len(improved)}"
        )

        print(
            f"Degraded : {len(degraded)}"
        )

        print(
            f"Unchanged: {len(unchanged)}"
        )

        print()

        # --------------------------------------------------
        # Cases improved by hybrid
        # --------------------------------------------------

        print("=" * 70)
        print("CASES IMPROVED BY HYBRID")
        print("=" * 70)

        for case, dense, hybrid in improved:

            print()
            print(case.id)
            print(case.question)

            print()
            print("Relevant:")
            print(
                sorted(
                    case.relevant_chunk_ids
                )
            )

            print()
            print("Dense:")
            print(
                dense.retrieved_chunk_ids
            )

            print()
            print("Hybrid:")
            print(
                hybrid.retrieved_chunk_ids
            )

        # --------------------------------------------------
        # Cases degraded by hybrid
        # --------------------------------------------------

        print()
        print("=" * 70)
        print("CASES DEGRADED BY HYBRID")
        print("=" * 70)

        for case, dense, hybrid in degraded:

            print()
            print(case.id)
            print(case.question)

            print()
            print("Relevant:")
            print(
                sorted(
                    case.relevant_chunk_ids
                )
            )

            print()
            print("Dense:")
            print(
                dense.retrieved_chunk_ids
            )

            print()
            print("Hybrid:")
            print(
                hybrid.retrieved_chunk_ids
            )

    finally:
        db.close()


if __name__ == "__main__":
    run_diff()