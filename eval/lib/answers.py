import re
from dataclasses import dataclass


NOT_FOUND_PHRASES = (
    "could not find",
    # The app's own fallback when an answer has no valid citation (app/rag/pipeline.py).
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
    "not specified",
)

# First sentence of the answer: up to the first ., ! or ? followed by
# whitespace or the end of the text.
_FIRST_SENTENCE = re.compile(r"^\s*(.*?(?:[.!?](?=\s|$)|$))", re.S)



@dataclass
class AnswerEvaluation:
    case_id: str
    expected_answerable: bool
    actual_answerable: bool
    correct: bool


def looks_like_refusal(answer: str) -> bool:
    """A refusal leads with "not found": only the first sentence is checked.

    An answer that gives the information and then adds a caveat ("... The
    exact calculation method is not specified in the policy.") is an answer,
    not a refusal. Checking the whole text counted such answers as refusals.
    """
    match = _FIRST_SENTENCE.match(answer)
    first_sentence = (match.group(1) if match else answer).lower()

    return any(
        phrase in first_sentence
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