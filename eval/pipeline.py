import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.db import SessionLocal
from app.rag import answer_question

from eval.answers import evaluate_refusal
from eval.answer_quality import evaluate_answer_quality
from eval.load import load_golden_cases
from eval.report import generate_report
from eval.regression import (
    MAX_RECALL_DROP,
    check_recall_regression,
)
from eval.retrieval import (
    calculate_metrics,
    evaluate_retrieval_case,
)


BASELINE_PATH = Path("eval/baseline.json")
LATEST_RUN_PATH = Path("eval/reports/latest.json")
LATEST_REPORT_PATH = Path("eval/reports/latest.md")


def run_evaluation(update_baseline: bool = False):

    cases = load_golden_cases()

    if not cases:
        raise ValueError("Golden set is empty.")

    db = SessionLocal()

    retrieval_results = []
    refusal_results = []
    quality_results = []

    try:
        for case in cases:

            print()
            print("=" * 60)
            print(case.id)
            print(case.question)
            print("=" * 60)

            # -------------------------------------------------
            # 1. Retrieval evaluation
            # -------------------------------------------------

            retrieval_result = evaluate_retrieval_case(
                db=db,
                case=case,
                top_k=5,
            )

            retrieval_results.append(
                retrieval_result
            )

            print(
                "Retrieved:",
                retrieval_result.retrieved_chunk_ids,
            )

            # -------------------------------------------------
            # 2. Full RAG answer
            # -------------------------------------------------

            rag_result = answer_question(
                db=db,
                question=case.question,
                top_k=5,
                min_score=0.45,
                max_context_tokens=3000,
            )

            print()
            print("Answer:")
            print(rag_result.answer)

            # -------------------------------------------------
            # 3. Refusal evaluation
            # -------------------------------------------------

            refusal_result = evaluate_refusal(
                case_id=case.id,
                expected_answerable=case.answerable,
                answer=rag_result.answer,
            )

            refusal_results.append(
                refusal_result
            )

            print(
                "Refusal correct:",
                refusal_result.correct,
            )

            # -------------------------------------------------
            # 4. Answer quality
            # -------------------------------------------------

            if rag_result.context:

                quality_result = (
                    evaluate_answer_quality(
                        case_id=case.id,
                        question=case.question,
                        answer=rag_result.answer,
                        context=rag_result.context,
                    )
                )

                if quality_result is None:
                    print("Judge returned invalid JSON, skipped")
                    continue

                quality_results.append(
                    quality_result
                )

                print(
                    f"Faithfulness: "
                    f"{quality_result.faithfulness:.2f}"
                )

                print(
                    f"Relevance: "
                    f"{quality_result.relevance:.2f}"
                )

                print(
                    f"Citation correctness: "
                    f"{quality_result.citation_correctness:.2f}"
                )

    finally:
        db.close()

    # =========================================================
    # Aggregate metrics
    # =========================================================

    retrieval_metrics = calculate_metrics(
        retrieval_results
    )

    refusal_accuracy = (
        sum(
            result.correct
            for result in refusal_results
        )
        / len(refusal_results)
    )

    if quality_results:

        faithfulness = (
            sum(
                result.faithfulness
                for result in quality_results
            )
            / len(quality_results)
        )

        relevance = (
            sum(
                result.relevance
                for result in quality_results
            )
            / len(quality_results)
        )

        citation_correctness = (
            sum(
                result.citation_correctness
                for result in quality_results
            )
            / len(quality_results)
        )

    else:
        faithfulness = 0.0
        relevance = 0.0
        citation_correctness = 0.0

    # =========================================================
    # Regression check against the previous baseline
    # =========================================================

    previous_baseline = None

    if BASELINE_PATH.exists():
        previous_baseline = json.loads(
            BASELINE_PATH.read_text(
                encoding="utf-8"
            )
        )

        previous_recall = previous_baseline[
            "retrieval"
        ]["recall_at_5"]

        regression_passed = check_recall_regression(
            baseline_recall=previous_recall,
            current_recall=retrieval_metrics.recall_at_5,
        )

    else:
        regression_passed = True

    # =========================================================
    # Results
    # =========================================================

    results = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),

        "dataset": {
            "cases": len(cases),
            "answerable_cases": sum(
                case.answerable
                for case in cases
            ),
            "unanswerable_cases": sum(
                not case.answerable
                for case in cases
            ),
        },

        "retrieval": {
            "recall_at_5": retrieval_metrics.recall_at_5,
            "mrr": retrieval_metrics.mrr,
        },

        "answers": {
            "refusal_accuracy": refusal_accuracy,
            "faithfulness": faithfulness,
            "relevance": relevance,
            "citation_correctness": citation_correctness,
        },

        "targets": {
            "recall_at_5": 0.85,
            "mrr": 0.70,
            "faithfulness": 0.90,
            "refusal_accuracy": 0.90,
        },

        "regression": {
            "recall_drop_threshold": MAX_RECALL_DROP,
            "passed": regression_passed,
        },
    }

    results_json = json.dumps(
        results,
        indent=2,
    )

    LATEST_RUN_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    LATEST_RUN_PATH.write_text(
        results_json,
        encoding="utf-8",
    )

    # Never overwrite the baseline implicitly: only create it on the
    # first run, or when explicitly asked with --update-baseline.
    baseline_written = (
        previous_baseline is None
        or update_baseline
    )

    if baseline_written:
        BASELINE_PATH.write_text(
            results_json,
            encoding="utf-8",
        )

    generate_report(
        results_path=str(LATEST_RUN_PATH),
        output_path=str(LATEST_REPORT_PATH),
        baseline_path=str(BASELINE_PATH),
    )

    # =========================================================
    # Print summary
    # =========================================================

    print()
    print()
    print("=" * 60)
    print("POLICY COPILOT — EVALUATION")
    print("=" * 60)

    print(
        f"Cases:              {len(cases)}"
    )

    print(
        f"Recall@5:           "
        f"{retrieval_metrics.recall_at_5:.4f}"
    )

    print(
        f"MRR:                "
        f"{retrieval_metrics.mrr:.4f}"
    )

    print(
        f"Faithfulness:       "
        f"{faithfulness:.4f}"
    )

    print(
        f"Relevance:          "
        f"{relevance:.4f}"
    )

    print(
        f"Citation correctness:"
        f" {citation_correctness:.4f}"
    )

    print(
        f"Refusal accuracy:   "
        f"{refusal_accuracy:.4f}"
    )

    print(
        f"Recall regression:  "
        f"{'PASS' if regression_passed else 'FAIL'}"
    )

    print()
    print(
        f"Saved results → "
        f"{LATEST_RUN_PATH}"
    )

    print(
        f"Saved report → "
        f"{LATEST_REPORT_PATH}"
    )

    if baseline_written:
        print(
            f"Saved baseline → "
            f"{BASELINE_PATH}"
        )
    else:
        print(
            f"Baseline unchanged ({BASELINE_PATH}); "
            f"use --update-baseline to replace it"
        )

    if not regression_passed:
        raise SystemExit(
            "Evaluation failed: "
            f"Recall@5 regression exceeded "
            f"{MAX_RECALL_DROP * 100:g} percentage points."
        )

    return results


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Replace eval/baseline.json with this run's results",
    )

    args = parser.parse_args()

    run_evaluation(
        update_baseline=args.update_baseline,
    )