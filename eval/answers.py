from dataclasses import dataclass


NOT_FOUND_PHRASES = (
    "could not find",
    "not found",
    "not available",
    "not enough information",
    "not supported",
)


@dataclass
class AnswerEvaluation:
    case_id: str
    expected_answerable: bool
    actual_answerable: bool
    correct: bool


def looks_like_refusal(answer: str) -> bool:

    normalized = answer.lower()

    return any(
        phrase in normalized
        for phrase in NOT_FOUND_PHRASES
    )


def evaluate_refusal(
    case_id: str,
    expected_answerable: bool,
    answer: str,
) -> AnswerEvaluation:

    actual_answerable = not looks_like_refusal(
        answer
    )

    return AnswerEvaluation(
        case_id=case_id,
        expected_answerable=expected_answerable,
        actual_answerable=actual_answerable,
        correct=(
            expected_answerable
            == actual_answerable
        ),
    )