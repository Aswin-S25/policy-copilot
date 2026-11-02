from app.db import SessionLocal

from eval.load import load_golden_cases
from eval.retrieval import (
    calculate_metrics,
    evaluate_retrieval_case,
)
from app.rag import answer_question
from eval.answers import evaluate_refusal
from eval.answer_quality import evaluate_answer_quality


def run_retrieval_evaluation():

    cases = load_golden_cases()

    db = SessionLocal()

    try:
        results = []

        for case in cases:

            result = evaluate_retrieval_case(
                db=db,
                case=case,
                top_k=5,
            )

            results.append(result)

            print(
                f"{case.id}: "
                f"{result.retrieved_chunk_ids}"
            )

        metrics = calculate_metrics(results)

        print()
        print("Retrieval Evaluation")
        print("---------------------")
        print(
            f"Recall@5: "
            f"{metrics.recall_at_5:.4f}"
        )
        print(
            f"MRR: "
            f"{metrics.mrr:.4f}"
        )

        return metrics

    finally:
        db.close()


def run_answer_evaluation():

    cases = load_golden_cases()

    db = SessionLocal()

    try:
        evaluations = []

        for case in cases:

            result = answer_question(
                db=db,
                question=case.question,
                top_k=5,
                min_score=0.45,
                max_context_tokens=3000,
            )

            evaluation = evaluate_refusal(
                case_id=case.id,
                expected_answerable=case.answerable,
                answer=result.answer,
            )

            evaluations.append(evaluation)

            print()
            print(case.id)
            print("Question:", case.question)
            print("Answer:", result.answer)
            print("Correct:", evaluation.correct)

        accuracy = (
            sum(
                item.correct
                for item in evaluations
            )
            / len(evaluations)
        )

        print()
        print("Refusal Accuracy")
        print("----------------")
        print(f"{accuracy:.4f}")

        return accuracy

    finally:
        db.close()


def run_quality_evaluation():

    cases = load_golden_cases()

    db = SessionLocal()

    try:
        results = []
        judge_failures = []

        for case in cases:

            rag_result = answer_question(
                db=db,
                question=case.question,
                top_k=5,
                min_score=0.45,
                max_context_tokens=3000,
            )

            if not rag_result.context:
                print(f"{case.id}: no context")
                continue

            quality = evaluate_answer_quality(
                case_id=case.id,
                question=case.question,
                answer=rag_result.answer,
                context=rag_result.context,
            )

            if quality is None:
                judge_failures.append(case.id)
                print(f"{case.id}: judge returned invalid JSON, skipped")
                continue

            results.append(quality)

            print()
            print(case.id)
            print(
                f"Faithfulness: "
                f"{quality.faithfulness:.2f}"
            )
            print(
                f"Relevance: "
                f"{quality.relevance:.2f}"
            )
            print(
                f"Citation correctness: "
                f"{quality.citation_correctness:.2f}"
            )

        if not results:
            return

        avg_faithfulness = (
            sum(r.faithfulness for r in results)
            / len(results)
        )

        avg_relevance = (
            sum(r.relevance for r in results)
            / len(results)
        )

        avg_citation_correctness = (
            sum(r.citation_correctness for r in results)
            / len(results)
        )

        print()
        print("Answer Quality")
        print("--------------")
        print(
            f"Faithfulness: "
            f"{avg_faithfulness:.4f}"
        )
        print(
            f"Relevance: "
            f"{avg_relevance:.4f}"
        )
        print(
            f"Citation correctness: "
            f"{avg_citation_correctness:.4f}"
        )
        print(
            f"Judged: {len(results)}, "
            f"judge failures: {len(judge_failures)}"
            + (f" ({', '.join(judge_failures)})" if judge_failures else "")
        )

        return results

    finally:
        db.close()

if __name__ == "__main__":
    run_quality_evaluation()
