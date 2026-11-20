import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.core.db import SessionLocal
from app.core.authz import ALL_ROLES
from app.rag.llm import LLMUnavailable
from app.rag.pipeline import answer_question

from eval.lib.answers import evaluate_refusal, looks_like_refusal
from eval.lib.answer_quality import evaluate_answer_quality
from eval.lib.load import load_golden_cases
from eval.lib.provenance import provenance
from eval.lib.report import generate_report
from eval.lib.regression import (
    check_regressions,
    floor_checks_passed,
    load_baseline_or_none,
    print_checks,
    targets,
)
from eval.lib.retrieval import (
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

    # Cases whose answer could not be generated or judged. Their share is
    # gated (coverage floors): averages over a small subset are not trusted.
    generation_failures = []
    judge_failures = []
    judge_attempts = 0

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
                strategy="hybrid",
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

            try:
                rag_result = answer_question(
                    db=db,
                    question=case.question,
                    top_k=5,
                    max_context_tokens=3000,
                    roles=ALL_ROLES,
                )
            except LLMUnavailable as exc:
                # One slow or failed generation must not abort the run.
                print(f"Answer generation failed, skipped: {exc}")
                generation_failures.append(case.id)
                db.rollback()
                continue

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

            # Refusals have no claims to judge; scoring them would count a
            # correct refusal as relevance 0 / citation correctness 0.
            if rag_result.context and not looks_like_refusal(rag_result.answer):

                judge_attempts += 1
                quality_result = (
                    evaluate_answer_quality(
                        case_id=case.id,
                        question=case.question,
                        answer=rag_result.answer,
                        context=rag_result.context,
                    )
                )

                if quality_result is None:
                    print("Judge failed (invalid JSON, timeout or connection), skipped")
                    judge_failures.append(case.id)
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
    # Results and gates
    # =========================================================

    current = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance(),
        "dataset": {
            "cases": len(cases),
            "answerable_cases": sum(case.answerable for case in cases),
            "unanswerable_cases": sum(not case.answerable for case in cases),
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
            "judged_answers": len(quality_results),
            "generation_failures": generation_failures,
            "judge_failures": judge_failures,
            # Share of cases that produced an answer / of judge attempts that
            # produced scores. Gated by floors in eval/lib/regression.py.
            "answer_coverage": 1 - len(generation_failures) / len(cases),
            "judge_coverage": (
                1 - len(judge_failures) / judge_attempts if judge_attempts else 1.0
            ),
        },
        "targets": targets(),
    }

    previous_baseline = load_baseline_or_none()
    checks = check_regressions(previous_baseline, current)
    print_checks(checks)

    # Replacing the baseline is judged on absolute floors only: the old
    # baseline may describe a different dataset, which is why it is replaced.
    passed = (
        floor_checks_passed(checks) if update_baseline
        else all(check.passed for check in checks)
    )

    results = {
        **current,
        "regression": {
            "passed": passed,
            "checks": [asdict(check) for check in checks],
        },
    }

    results_json = json.dumps(results, indent=2)

    LATEST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_RUN_PATH.write_text(results_json, encoding="utf-8")

    # Never overwrite the baseline implicitly, and never with a run that
    # misses an absolute floor.
    baseline_written = (previous_baseline is None or update_baseline) and passed
    if baseline_written:
        BASELINE_PATH.write_text(results_json, encoding="utf-8")

    generate_report(
        results_path=str(LATEST_RUN_PATH),
        output_path=str(LATEST_REPORT_PATH),
        baseline_path=str(BASELINE_PATH),
    )

    print()
    print("=" * 60)
    print("POLICY COPILOT - EVALUATION")
    print("=" * 60)
    print(f"Cases:                {len(cases)}")
    print(f"Recall@5:             {retrieval_metrics.recall_at_5:.4f}")
    print(f"MRR:                  {retrieval_metrics.mrr:.4f}")
    print(f"Refusal accuracy:     {refusal_accuracy:.4f}")
    print(f"Faithfulness:         {faithfulness:.4f}")
    print(f"Relevance:            {relevance:.4f}")
    print(f"Citation correctness: {citation_correctness:.4f}")
    print(f"Judged answers:       {len(quality_results)}")
    print(f"Generation failures:  {len(generation_failures)} {generation_failures or ''}")
    print(f"Judge failures:       {len(judge_failures)} {judge_failures or ''}")
    print(f"Gates:                {'PASS' if passed else 'FAIL'}")
    print(f"Saved results -> {LATEST_RUN_PATH}")
    print(f"Saved report  -> {LATEST_REPORT_PATH}")
    print(
        f"Saved baseline -> {BASELINE_PATH}" if baseline_written
        else f"Baseline unchanged ({BASELINE_PATH})"
    )

    if not passed:
        failed = [c.metric + f" ({c.kind})" for c in checks if not c.passed]
        raise SystemExit("Evaluation failed: " + ", ".join(failed))

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Replace eval/baseline.json with this run (requires all floors to pass)",
    )
    args = parser.parse_args()
    run_evaluation(update_baseline=args.update_baseline)
