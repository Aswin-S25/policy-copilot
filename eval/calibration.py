import json
from dataclasses import dataclass
from pathlib import Path

from eval.judge import judge_answer

@dataclass
class CalibrationCase:
    id: str
    question: str
    answer: str
    context: str
    human_faithfulness: float
    human_relevance: float
    human_citation_correctness: float


@dataclass
class CalibrationResult:
    case_id: str
    human_faithfulness: float
    judge_faithfulness: float
    
    human_relevance: float
    judge_relevance: float
    
    human_citation_correctness: float
    judge_citation_correctness: float


def load_calibration_cases(
    path: str = "eval/judge_calibration.json",
) -> list[CalibrationCase]:
    
    data = json.loads(
        Path(path).read_text(
            encoding='utf-8'
        )
    )
    
    return [
        CalibrationCase(
            id=item["id"],
            question=item["question"],
            answer=item["answer"],
            context=item["context"],
            human_faithfulness=item["human_faithfulness"],
            human_relevance=item["human_relevance"],
            human_citation_correctness=item[
                "human_citation_correctness"
            ],
        )
        for item in data
    ]

def absolute_error(
    human: float,
    judge: float
) -> float:
    return abs(human - judge)



def classify_score(score: float) -> str:
    if score >= 0.8:
        return "good"

    if score >= 0.5:
        return "partial"

    return "bad"

def classification_accuracy(
    human_scores: list[float],
    judge_scores: list[float],
) -> float:

    if not human_scores:
        return 0.0

    correct = 0

    for human, judge in zip(
        human_scores,
        judge_scores,
    ):
        if classify_score(human) == classify_score(judge):
            correct += 1

    return correct / len(human_scores)


def run_calibration():
    cases = load_calibration_cases()
    
    results = []

    for case in cases:
        
        judge = judge_answer(
            question=case.question,
            answer=case.answer,
            context=case.context,
        )
        
        result = CalibrationResult(
            case_id=case.id,
            
            human_faithfulness=case.human_faithfulness,
            judge_faithfulness=judge.faithfulness,

            human_relevance=case.human_relevance,
            judge_relevance=judge.relevance,

            human_citation_correctness=(
                case.human_citation_correctness
            ),
            judge_citation_correctness=(
                judge.citation_correctness
            ),
        )
        
        results.append(result)
        
        print()
        print(case.id)
        
        print(
            f"Faithfulness: "
            f"human={case.human_faithfulness:.2f} "
            f"judge={judge.faithfulness:.2f}"
        )

        print(
            f"Relevance: "
            f"human={case.human_relevance:.2f} "
            f"judge={judge.relevance:.2f}"
        )

        print(
            f"Citation: "
            f"human={case.human_citation_correctness:.2f} "
            f"judge={judge.citation_correctness:.2f}"
        )

    if not results:
        print("No calibration cases found.")
        return
    
    
    faithfulness_error = sum(
         absolute_error(
                r.human_faithfulness,
                r.judge_faithfulness,
            )
            for r in results
        ) / len(results)

    relevance_error = sum(
        absolute_error(
            r.human_relevance,
            r.judge_relevance,
        )
        for r in results
    ) / len(results)
    
    citation_error = sum(
        absolute_error(
            r.human_citation_correctness,
            r.judge_citation_correctness,
        )
        for r in results
    ) / len(results)
    
    
    faithfulness_classification_accuracy = (
        classification_accuracy(
            [
                r.human_faithfulness
                for r in results
            ],
            [
                r.judge_faithfulness
                for r in results
            ],
        )
    )
    
    print()
    print("=" * 55)
    print("JUDGE CALIBRATION")
    print("=" * 55)

    print(
        f"Faithfulness MAE: "
        f"{faithfulness_error:.4f}"
    )

    print(
        f"Relevance MAE: "
        f"{relevance_error:.4f}"
    )

    print(
        f"Citation MAE: "
        f"{citation_error:.4f}"
    )
    
    print(
        f"Faithfulness classification accuracy: "
        f"{faithfulness_classification_accuracy:.4f}"
    )

    print("=" * 55)

    return results



if __name__ == "__main__":
    run_calibration()
