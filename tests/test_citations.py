from app.citations import (
    exact_citations,
    remove_invalid_citations,
    validate_citations,
)


def test_extract_citations():
    answer = (
        "Employees receive annual leave [Source 1]. "
        "Requests require manager approval [Source 2]."
    )

    assert exact_citations(answer) == {1, 2}


def test_valid_citations():
    answer = "Employees receive annual leave [Source 1]."

    assert validate_citations(
        answer,
        {1, 2, 3},
    )


def test_invalid_citation():
    answer = "Employees receive annual leave [Source 7]."

    assert not validate_citations(
        answer,
        {1, 2, 3},
    )


def test_remove_invalid_citations():
    answer = (
        "Annual leave is 20 days [Source 1]. "
        "Something else [Source 9]."
    )

    cleaned = remove_invalid_citations(
        answer,
        {1},
    )

    assert "[Source 1]" in cleaned
    assert "[Source 9]" not in cleaned