from dataclasses import dataclass


NOT_FOUND_PHRASES = (
    "could not find",
    # The app's own fallback when an answer has no valid citation (app/rag.py).
    "could not produce",
    "not found",
    "not available",
    "not enough information",
    "not supported",
    # Natural-language refusals the model actually produces.
    "do not specify", "does not specify",
    "do not contain", "does not contain",
    "do not mention", "does not mention",
    "do not address", "does not address",
    "do not provide", "does not provide",
    "do not state", "does not state",
    "do not include", "does not include",
    "no information", "no specific information",
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