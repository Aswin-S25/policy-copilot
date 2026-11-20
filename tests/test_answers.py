import pytest

from eval.answers import looks_like_refusal


@pytest.mark.parametrize("answer", [
    "I could not produce a sufficiently supported answer from the available policies.",
    "I could not find relevant information in the available policies.",
    "The provided policies do not specify the number of weeks of paid parental leave.",
    "The provided policy sources do not contain specific information about the office dress code.",
    "The policy sources do not mention ISS-08.",
])
def test_refusals_are_detected(answer):
    assert looks_like_refusal(answer)


@pytest.mark.parametrize("answer", [
    "Employees receive 24 days of annual leave per year [Source 1].",
    "Up to 5 unused days can be carried forward to the next year [Source 2].",
])
def test_direct_answers_are_not_refusals(answer):
    assert not looks_like_refusal(answer)


# Real answers from the 138-case baseline run.

def test_refusal_phrased_as_not_specified_is_detected():
    answer = (
        "The notice period for resignation is not specified in the provided "
        "policy sources. The available information addresses notice periods "
        "for ending hybrid arrangements [Source 1]."
    )
    assert looks_like_refusal(answer)


@pytest.mark.parametrize("answer", [
    # Full answer, then a caveat: an answer, not a refusal.
    "If you resign within 12 months, you must repay the amount pro rata "
    "[Source 1]. The exact calculation method is not specified in the policy.",
    "The policy prohibits accepting gifts that could influence a decision "
    "[Source 1]. However, the provided policies do not specify disciplinary "
    "consequences.",
])
def test_answer_followed_by_caveat_is_not_a_refusal(answer):
    assert not looks_like_refusal(answer)


def test_only_first_sentence_counts_even_without_final_period():
    assert looks_like_refusal("I could not find relevant information")
    assert not looks_like_refusal("Employees get 24 days [Source 1]. Other details not found")
