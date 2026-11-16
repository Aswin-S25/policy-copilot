
from app.db import SessionLocal

from eval.load import load_golden_cases
from eval.retrieval import evaluate_retrieval_case


STRATEGIES = ["dense", "lexical", "hybrid"]




def calculate_case_metrics(result):
    relevant = set(result.relevant_chunk_ids)
    retrieved = result.retrieved_chunk_ids

    if not relevant:
        return None, None

    hits = relevant.intersection(retrieved)
    recall = len(hits) / len(relevant)

    reciprocal_rank = 0.0

    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant:
            reciprocal_rank = 1.0 / rank
            break

    return recall, reciprocal_rank



def run_hybrid_diagnostics():

    cases = load_golden_cases()
    db = SessionLocal()

    metrics = {
        strategy: {
            "recall": [],
            "mrr": [],
        }
        for strategy in STRATEGIES
    }

    hybrid_better = 0
    hybrid_worse = 0
    hybrid_same = 0
    skipped = 0

    try:
        print("=" * 90)
        print("DENSE vs LEXICAL vs HYBRID RETRIEVAL DIAGNOSTICS")
        print("=" * 90)

        for case in cases:

            # Unanswerable cases have no relevant chunks, so Recall@5
            # and MRR are undefined (None) and can't be compared.
            if not case.relevant_chunk_ids:
                skipped += 1
                continue

            case_results = {}

            for strategy in STRATEGIES:

                result = evaluate_retrieval_case(
                    db=db,
                    case=case,
                    top_k=5,
                    strategy=strategy,
                )

                recall, mrr = calculate_case_metrics(result)
                if recall is not None:
                    metrics[strategy]["recall"].append(recall)
                    metrics[strategy]["mrr"].append(mrr)


                case_results[strategy] = {
                    "recall": recall,
                    "mrr": mrr,
                }

            dense_recall = case_results["dense"]["recall"]
            lexical_recall = case_results["lexical"]["recall"]
            hybrid_recall = case_results["hybrid"]["recall"]

            if hybrid_recall > dense_recall:
                hybrid_better += 1
                status = "HYBRID BETTER THAN DENSE"
            elif hybrid_recall < dense_recall:
                hybrid_worse += 1
                status = "HYBRID WORSE THAN DENSE"
            else:
                hybrid_same += 1
                status = "SAME RECALL AS DENSE"

            print()
            print("-" * 90)
            print(f"Case: {case.id}")
            print(f"Query: {case.question}")
            print(f"Status: {status}")

            for strategy in STRATEGIES:
                result = case_results[strategy]

                print(
                    f"{strategy.upper():8} | "
                    f"Recall@5: {result['recall']:.4f} | "
                    f"MRR: {result['mrr']:.4f}"
                )

        print()
        print("=" * 90)
        print("AGGREGATE RESULTS")
        print("=" * 90)

        for strategy in STRATEGIES:

            recall_values = metrics[strategy]["recall"]
            mrr_values = metrics[strategy]["mrr"]

            avg_recall = sum(recall_values) / len(recall_values)
            avg_mrr = sum(mrr_values) / len(mrr_values)

            print(
                f"{strategy.upper():8} | "
                f"Average Recall@5: {avg_recall:.4f} | "
                f"Average MRR: {avg_mrr:.4f}"
            )

        print()
        print("=" * 90)
        print("HYBRID vs DENSE SUMMARY")
        print("=" * 90)

        print(f"Total cases: {len(cases)}")
        print(f"Evaluated (answerable): {len(cases) - skipped}")
        print(f"Skipped (unanswerable): {skipped}")
        print(f"Hybrid better: {hybrid_better}")
        print(f"Hybrid worse: {hybrid_worse}")
        print(f"Same recall: {hybrid_same}")

    finally:
        db.close()


if __name__ == "__main__":
    run_hybrid_diagnostics()
