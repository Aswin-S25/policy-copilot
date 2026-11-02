from dataclasses import dataclass

from eval.judge import judge_answer


@dataclass
class AnswerQualityResult:
    case_id: str
    faithfulness: float
    relevance: float
    citation_correctness: float


def evaluate_answer_quality(
    case_id: str,
    question: str,
    answer: str,
    context: str,
) -> AnswerQualityResult | None:

    result = judge_answer(
        question=question,
        answer=answer,
        context=context,
    )

    if result is None:
        return None

    return AnswerQualityResult(
        case_id=case_id,
        faithfulness=result.faithfulness,
        relevance=result.relevance,
        citation_correctness=result.citation_correctness,
    )