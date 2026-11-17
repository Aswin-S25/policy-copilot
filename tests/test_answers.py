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
