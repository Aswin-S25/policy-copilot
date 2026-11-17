"""The answer pipeline shared by /talk and /ask/stream (LLM stubbed out)."""
from uuid import uuid4

import app.rag as rag
from app.retrieval import RetrievedChunk


def make_chunk(content="Employees receive 24 days of annual leave per year."):
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Handbook",
        section_path="1. Leave > 1.1 Annual Leave",
        content=content,
        chunk_index=0,
        score=0.03,
    )


# ---- finalize_answer --------------------------------------------------------

def test_finalize_keeps_valid_citations():
    context, _ = rag.context_or_refusal([make_chunk()], 3000)

    answer = rag.finalize_answer("You get 24 days [Source 1].", context)

    assert answer == "You get 24 days [Source 1]."


def test_finalize_strips_citations_to_missing_sources():
    context, _ = rag.context_or_refusal([make_chunk()], 3000)

    answer = rag.finalize_answer("24 days [Source 1] or 30 [Source 7].", context)

    assert "[Source 7]" not in answer
    assert "[Source 1]" in answer


def test_finalize_refuses_uncited_answer():
    context, _ = rag.context_or_refusal([make_chunk()], 3000)

    answer = rag.finalize_answer("You get 24 days.", context)

    assert answer == rag.UNSUPPORTED_REFUSAL


# ---- context_or_refusal -------------------------------------------------------

def test_no_chunks_is_refused_without_context():
    context, refusal = rag.context_or_refusal([], 3000)

    assert context is None
    assert refusal == rag.NO_CONTEXT_REFUSAL


def test_chunk_larger_than_budget_is_refused():
    context, refusal = rag.context_or_refusal([make_chunk("x" * 4000)], 10)

    assert context is None
    assert refusal == rag.CONTEXT_TOO_SMALL_REFUSAL


# ---- answer_question ----------------------------------------------------------

def test_answer_question_uses_search_policies_with_roles(monkeypatch):
    seen = {}

    def fake_search(**kwargs):
        seen.update(kwargs)
        return [make_chunk()]

    monkeypatch.setattr(rag, "search_policies", fake_search)
    monkeypatch.setattr(rag, "generate_answer", lambda **_: "24 days [Source 1].")

    response = rag.answer_question(db=None, question="q", roles=["hr"])

    assert seen["roles"] == ["hr"]
    assert response.answer == "24 days [Source 1]."
    assert [c.source_number for c in response.citations] == [1]


# ---- stream_answer_events -----------------------------------------------------

def stream_of(*tokens):
    return lambda **_: iter(tokens)


def test_stream_emits_tokens_then_validated_answer_and_citations(monkeypatch):
    monkeypatch.setattr(rag, "stream_answer", stream_of("24 days ", "[Source 1]."))

    events = list(rag.stream_answer_events("q", [make_chunk()]))
    names = [name for name, _ in events]

    assert names == ["status", "token", "token", "answer", "citations"]
    assert events[3][1] == {"text": "24 days [Source 1]."}
    assert events[4][1]["sources"][0]["source"] == 1


def test_stream_final_answer_matches_blocking_rules(monkeypatch):
    # Uncited output is streamed as tokens, but the authoritative final
    # answer is the same refusal /talk would return.
    monkeypatch.setattr(rag, "stream_answer", stream_of("Probably 24 days."))

    events = dict(rag.stream_answer_events("q", [make_chunk()]))

    assert events["answer"] == {"text": rag.UNSUPPORTED_REFUSAL}


def test_stream_without_chunks_refuses_without_calling_llm(monkeypatch):
    def must_not_run(**_):
        raise AssertionError("LLM must not be called without context")

    monkeypatch.setattr(rag, "stream_answer", must_not_run)

    events = list(rag.stream_answer_events("q", []))

    assert events == [("answer", {"text": rag.NO_CONTEXT_REFUSAL})]
