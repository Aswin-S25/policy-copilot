import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import app.api.conversations as conversation_api
import app.conversations.service as conversation_service
import app.rag.pipeline as rag
from app.main import app
from app.conversations.repository import append_message, create_conversation, get_messages
from app.core.models import Chunk
from app.core.security import create_access_token
from app.rag.llm import LLMUnavailable
from ingest.embed import embed_document_chunks
from ingest.models import ParsedDocument, ParsedSection
from ingest.upsert import ingest_document

client = TestClient(app)

PUBLIC = "Employees receive 24 days of annual leave per year."
RESTRICTED = "SEV1 incidents must be acknowledged within 15 minutes by the on-call engineer."
STUB_ANSWER = "Stub answer [Source 1]."


def bearer(sub, roles):
    return {"Authorization": f"Bearer {create_access_token(sub, roles)}"}


def ingest(db, source, text, roles):
    document = ingest_document(
        db,
        ParsedDocument(
            title=source, source=source, document_type="markdown", content=text,
            sections=[ParsedSection(title="S", level=2, content=text, position=0)],
        ),
        allowed_roles=roles,
    )
    embed_document_chunks(db, document.id)
    return set(db.scalars(select(Chunk.id).where(Chunk.document_id == document.id)))


@pytest.fixture
def sessions(db, monkeypatch):
    """Point the API at the test database."""
    factory = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr(conversation_api, "SessionLocal", factory)
    return factory


@pytest.fixture
def corpus(db, sessions):
    return {
        "public": ingest(db, "leave.md", PUBLIC, ["employee", "security"]),
        "restricted": ingest(db, "ir.md", RESTRICTED, ["security"]),
    }


@pytest.fixture
def llm(monkeypatch):
    """Stub every LLM call and record the rewrite prompts."""
    calls = {"rewrite_prompts": [], "rewrite_answer": "REWRITTEN QUESTION"}

    def fake_complete(**kwargs):
        calls["rewrite_prompts"].append(kwargs["user_prompt"])
        return calls["rewrite_answer"]

    monkeypatch.setattr(conversation_service, "complete", fake_complete)
    monkeypatch.setattr(rag, "generate_answer", lambda **_: STUB_ANSWER)
    monkeypatch.setattr(rag, "stream_answer", lambda **_: iter(["Stub ", "answer [Source 1]."]))
    return calls


def new_conversation(sub, roles):
    response = client.post("/conversations", json={}, headers=bearer(sub, roles))
    assert response.status_code == 201
    return response.json()["id"]


def ask(conversation_id, sub, roles, question):
    return client.post(
        f"/conversations/{conversation_id}/messages",
        json={"question": question},
        headers=bearer(sub, roles),
    )


def stored_messages(sessions, conversation_id, sub="alice"):
    with sessions() as s:
        return get_messages(s, uuid.UUID(conversation_id), sub)


# ---- authentication and ownership -------------------------------------------

def test_conversation_endpoints_require_token():
    assert client.get("/conversations").status_code == 401
    assert client.post("/conversations", json={}).status_code == 401


def test_other_user_gets_404_everywhere(sessions, llm):
    conversation_id = new_conversation("alice", ["employee"])
    mallory = bearer("mallory", ["employee", "security"])

    foreign = client.get(f"/conversations/{conversation_id}", headers=mallory)
    missing = client.get(f"/conversations/{uuid.uuid4()}", headers=mallory)

    # Indistinguishable from a conversation that does not exist.
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()

    assert client.delete(f"/conversations/{conversation_id}", headers=mallory).status_code == 404
    assert client.post(f"/conversations/{conversation_id}/messages",
                       json={"question": "q"}, headers=mallory).status_code == 404
    assert client.post(f"/conversations/{conversation_id}/messages/stream",
                       json={"question": "q"}, headers=mallory).status_code == 404
    assert client.get("/conversations", headers=mallory).json()["conversations"] == []

    # Nothing was written to alice's conversation.
    assert stored_messages(sessions, conversation_id) == []


def test_message_validation(sessions):
    conversation_id = new_conversation("alice", ["employee"])
    url = f"/conversations/{conversation_id}/messages"
    headers = bearer("alice", ["employee"])

    assert client.post(url, json={"question": ""}, headers=headers).status_code == 422
    assert client.post(url, json={"question": "q", "top_k": 500}, headers=headers).status_code == 422
    assert client.post(url, json={"question": "q", "roles": ["security"]},
                       headers=headers).status_code == 422


def test_delete_conversation(sessions):
    conversation_id = new_conversation("alice", ["employee"])
    headers = bearer("alice", ["employee"])

    assert client.delete(f"/conversations/{conversation_id}", headers=headers).status_code == 204
    assert client.get(f"/conversations/{conversation_id}", headers=headers).status_code == 404


# ---- turns ------------------------------------------------------------------------

def test_first_turn_stores_question_and_answer_with_sources(sessions, corpus, llm):
    conversation_id = new_conversation("alice", ["employee"])

    response = ask(conversation_id, "alice", ["employee"], "How many days of annual leave?")

    assert response.status_code == 200
    assert response.json()["standalone_question"] == "How many days of annual leave?"
    assert llm["rewrite_prompts"] == []  # no history: no rewrite call

    conversation = client.get(f"/conversations/{conversation_id}",
                              headers=bearer("alice", ["employee"])).json()
    assert conversation["title"] == "How many days of annual leave?"
    assert [m["sender"] for m in conversation["messages"]] == ["user", "assistant"]

    answer = stored_messages(sessions, conversation_id)[1]
    assert answer.source_chunk_ids
    assert set(answer.source_chunk_ids) <= corpus["public"]


def test_follow_up_is_rewritten_with_history(sessions, corpus, llm):
    conversation_id = new_conversation("alice", ["employee"])
    ask(conversation_id, "alice", ["employee"], "How many days of annual leave?")

    llm["rewrite_answer"] = "Can unused annual leave be carried forward?"
    body = ask(conversation_id, "alice", ["employee"], "Can I carry it forward?").json()

    assert body["standalone_question"] == "Can unused annual leave be carried forward?"
    assert "How many days of annual leave?" in llm["rewrite_prompts"][0]
    assert STUB_ANSWER in llm["rewrite_prompts"][0]


def test_revoked_role_hides_old_answers_and_keeps_them_out_of_new_turns(
    sessions, corpus, llm
):
    conversation_id = new_conversation("alice", ["security"])
    ask(conversation_id, "alice", ["security"], "How fast must SEV1 be acknowledged?")

    first_answer = stored_messages(sessions, conversation_id)[1]
    assert set(first_answer.source_chunk_ids) & corpus["restricted"]

    # Same user, security role removed.
    employee = bearer("alice", ["employee"])

    shown = client.get(f"/conversations/{conversation_id}", headers=employee).json()
    assert shown["messages"][1]["withheld"] is True
    assert STUB_ANSWER not in shown["messages"][1]["content"]
    assert "standalone_question" not in shown["messages"][0]

    llm["rewrite_answer"] = "How fast must SEV2 be acknowledged?"
    ask(conversation_id, "alice", ["employee"], "And SEV2?")

    assert STUB_ANSWER not in llm["rewrite_prompts"][-1]
    latest = stored_messages(sessions, conversation_id)[-1]
    assert not set(latest.source_chunk_ids) & corpus["restricted"]


def test_history_returns_citations_for_visible_answers(sessions, corpus, llm):
    conversation_id = new_conversation("alice", ["employee"])
    ask(conversation_id, "alice", ["employee"], "How many days of annual leave?")

    shown = client.get(f"/conversations/{conversation_id}",
                       headers=bearer("alice", ["employee"])).json()
    question, answer = shown["messages"]
    assert question["citations"] == []

    # "[Source N]" in the answer is the N-th stored context chunk.
    stored = stored_messages(sessions, conversation_id)[1]
    assert [c["source"] for c in answer["citations"]] == list(
        range(1, len(stored.source_chunk_ids) + 1)
    )
    assert [c["chunk_id"] for c in answer["citations"]] == [
        str(chunk_id) for chunk_id in stored.source_chunk_ids
    ]
    first = answer["citations"][0]
    # Stored title "leave.md" is a file name: shown as the first heading.
    assert first["document"] == "S"
    assert first["section"] == "S"
    assert first["score"] is None  # not stored for history


def test_withheld_answer_reveals_no_citations(sessions, corpus, llm):
    conversation_id = new_conversation("alice", ["security"])
    ask(conversation_id, "alice", ["security"], "How fast must SEV1 be acknowledged?")

    shown = client.get(f"/conversations/{conversation_id}",
                       headers=bearer("alice", ["employee"])).json()
    answer = shown["messages"][1]
    assert answer["withheld"] is True
    assert answer["citations"] == []  # not even the readable document's title


def test_stream_turn_emits_events_and_saves_answer(sessions, corpus, llm):
    conversation_id = new_conversation("alice", ["employee"])

    response = client.post(
        f"/conversations/{conversation_id}/messages/stream",
        json={"question": "How many days of annual leave?"},
        headers=bearer("alice", ["employee"]),
    )

    assert response.status_code == 200
    names = [line[7:] for line in response.text.splitlines() if line.startswith("event: ")]
    assert names[0] == "status"
    assert names[-1] == "done"
    for expected in ("question", "token", "answer", "citations", "saved"):
        assert expected in names

    contents = [m.content for m in stored_messages(sessions, conversation_id)]
    assert contents == ["How many days of annual leave?", STUB_ANSWER]


# ---- concurrency --------------------------------------------------------------------

def test_concurrent_appends_get_unique_sequential_positions(sessions):
    with sessions() as s:
        conversation_id = create_conversation(s, "alice").id
        s.commit()

    barrier = threading.Barrier(5)
    errors = []

    def worker(n):
        try:
            barrier.wait()
            for i in range(4):
                with sessions() as s:
                    append_message(s, conversation_id, "alice",
                                   sender="user", content=f"{n}-{i}")
                    s.commit()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    with sessions() as s:
        positions = [m.position for m in get_messages(s, conversation_id, "alice")]
    assert positions == list(range(20))




def raise_unavailable(**_):
    raise LLMUnavailable("ollama 503: model loading")


def test_talk_returns_503_with_generic_message(monkeypatch):
    from app.retrieval.dense import RetrievedChunk

    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), document_title="H",
        section_path="S", content=PUBLIC, chunk_index=0, score=0.03,
    )
    monkeypatch.setattr(rag, "search_policies", lambda **_: [chunk])
    monkeypatch.setattr(rag, "generate_answer", raise_unavailable)

    response = client.post("/talk", json={"question": "q"},
                           headers=bearer("alice", ["employee"]))

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "10"
    assert "model loading" not in response.text  # internal detail not exposed


def test_blocking_turn_failure_discards_question(sessions, corpus, llm, monkeypatch):
    monkeypatch.setattr(rag, "generate_answer", raise_unavailable)
    conversation_id = new_conversation("alice", ["employee"])

    response = ask(conversation_id, "alice", ["employee"], "How many days of annual leave?")

    assert response.status_code == 503
    assert stored_messages(sessions, conversation_id) == []


def test_stream_turn_failure_emits_error_and_discards_question(
    sessions, corpus, llm, monkeypatch
):
    def failing_stream(**_):
        yield "Partial "
        raise LLMUnavailable("ReadTimeout")

    monkeypatch.setattr(rag, "stream_answer", failing_stream)
    conversation_id = new_conversation("alice", ["employee"])

    response = client.post(
        f"/conversations/{conversation_id}/messages/stream",
        json={"question": "How many days of annual leave?"},
        headers=bearer("alice", ["employee"]),
    )

    names = [line[7:] for line in response.text.splitlines() if line.startswith("event: ")]
    assert "error" in names
    assert "answer" not in names and "saved" not in names
    assert names[-1] == "done"
    assert stored_messages(sessions, conversation_id) == []


def test_failed_turn_can_be_retried_cleanly(sessions, corpus, llm, monkeypatch):
    conversation_id = new_conversation("alice", ["employee"])

    monkeypatch.setattr(rag, "generate_answer", raise_unavailable)
    assert ask(conversation_id, "alice", ["employee"], "Leave days?").status_code == 503

    monkeypatch.setattr(rag, "generate_answer", lambda **_: STUB_ANSWER)
    assert ask(conversation_id, "alice", ["employee"], "Leave days?").status_code == 200

    assert [m.position for m in stored_messages(sessions, conversation_id)] == [0, 1]
