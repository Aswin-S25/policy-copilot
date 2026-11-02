from app.db import SessionLocal

from eval.load import load_golden_cases
from eval.retrieval import (
    calculate_metrics,
    evaluate_retrieval_case,
)
from app.rag import answer_question
from eval.answers import evaluate_refusal


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

if __name__ == "__main__":
    run_retrieval_evaluation()