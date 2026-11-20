
import pytest

from app.retrieval.experimental.query_planner import plan_query


@pytest.mark.parametrize(
    "query",
    [
        "Find policy AL-03",
        "What does policy HR_2024 say?",
        "Show me document POL-123",
        "Explain rule SEC-12A",
    ],
)
def test_structured_identifiers_use_lexical_retrieval(query):
    plan = plan_query(query)

    assert plan.strategy == "lexical"
    assert plan.reason == "Contains a structured identifier or policy code"


@pytest.mark.parametrize(
    "query",
    [
        "What are the working hours?",
        "What is the reimbursement policy?",
        "Explain attendance rules",
        "How many days of leave can I take?",
    ],
)
def test_natural_language_queries_use_hybrid_retrieval(query):
    plan = plan_query(query)

    assert plan.strategy == "hybrid"
    assert plan.reason == "Uses natural-language retrieval"


def test_query_with_identifier_inside_sentence_uses_lexical():
    plan = plan_query("Can you explain policy AL-03 to me?")

    assert plan.strategy == "lexical"


def test_query_with_lowercase_identifier_uses_hybrid():
    plan = plan_query("Find policy al-03")

    assert plan.strategy == "hybrid"


def test_empty_query_uses_hybrid():
    plan = plan_query("")

    assert plan.strategy == "hybrid"
