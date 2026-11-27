from app.rag.citations import (
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

def test_native_gpt_oss_citations_are_normalized():
    from app.rag.citations import normalize_citations

    assert normalize_citations("24 days【Source 1】.") == "24 days[Source 1]."
    assert normalize_citations("Approval【Source 2†L3-L5】 and 【 Source 3 】") == (
        "Approval[Source 2] and [Source 3]"
    )
    # Unrelated brackets and plain text are untouched.
    assert normalize_citations("Section【Annex A】 [Source 4]") == "Section【Annex A】 [Source 4]"
    assert normalize_citations("【Source 1 never closed") == "【Source 1 never closed"


def test_native_citations_survive_answer_validation():
    from app.rag.context import build_context
    from app.rag.pipeline import UNSUPPORTED_REFUSAL, finalize_answer
    from app.retrieval.dense import RetrievedChunk
    import uuid

    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), document_title="Handbook",
        section_path="Leave", chunk_index=0, content="24 days of annual leave.", score=0.9,
    )
    context = build_context([chunk], max_tokens=3000)

    # The exact raw output gpt-oss-120b produced on the live deployment.
    raw = "Full-time employees receive **24 working days of annual leave per calendar year**【Source 1】."
    answer = finalize_answer(raw, context)
    assert answer != UNSUPPORTED_REFUSAL
    assert answer.endswith("[Source 1].")
    # A citation to a source that wasn't provided is still removed.
    assert finalize_answer("Made up【Source 7】.", context) == UNSUPPORTED_REFUSAL
