import json
import logging
import re
import uuid

import pytest
from fastapi.testclient import TestClient

import app.api as api
import app.rag as rag
from app.api import app
from app.llm import LLMUnavailable
from app.observability import JsonFormatter, record, request_context, stage
from app.retrieval import RetrievedChunk
from app.security import create_access_token

client = TestClient(app)
FORMATTER = JsonFormatter()

CANARY_QUESTION = "CANARY-Q-7781 how many leave days?"
CANARY_DOC = "CANARY-DOC-5531 employees receive 24 days."
CANARY_ANSWER = "CANARY-A-9912 24 days [Source 1]."


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def employee_token():
    return create_access_token("alice", ["employee"])


def lines(caplog):
    return [json.loads(FORMATTER.format(r)) for r in caplog.records]


def completed(caplog):
    return [l for l in lines(caplog) if l["event"] == "request_completed"]


@pytest.fixture
def stub_rag(monkeypatch):
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), document_title="H",
        section_path="S", content=CANARY_DOC, chunk_index=0, score=0.03,
    )
    monkeypatch.setattr(rag, "search_policies", lambda **_: [chunk])
    monkeypatch.setattr(api, "search_policies", lambda **_: [chunk])
    monkeypatch.setattr(rag, "generate_answer", lambda **_: CANARY_ANSWER)
    monkeypatch.setattr(
        rag, "stream_answer", lambda **_: iter(["CANARY-A-9912 ", "[Source 1]."])
    )
    return chunk


# ---- building blocks -------------------------------------------------------------

def test_formatter_emits_one_json_object_with_request_id_and_fields():
    logger = logging.getLogger("test")
    with request_context("req-1"):
        rec = logger.makeRecord("test", logging.INFO, __file__, 1,
                                "something_happened", None, None,
                                extra={"retrieved": 5})

    line = json.loads(FORMATTER.format(rec))

    assert line["event"] == "something_happened"
    assert line["level"] == "INFO"
    assert line["request_id"] == "req-1"
    assert line["retrieved"] == 5


def test_stage_and_record_accumulate_in_request_and_noop_outside():
    record(ignored=True)  # no request: must not fail
    with stage("ignored"):
        pass

    with request_context("req-2") as ctx:
        with stage("retrieval"):
            pass
        with stage("retrieval"):
            pass
        record(retrieved=3)

    assert "retrieval_ms" in ctx["stages"]
    assert ctx["fields"] == {"retrieved": 3}


# ---- request IDs -------------------------------------------------------------------

def test_request_id_is_generated_and_safe_ids_are_echoed():
    generated = client.get("/health").headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", generated)

    echoed = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert echoed.headers["x-request-id"] == "trace-abc-123"


@pytest.mark.parametrize("unsafe", ["has space", "x" * 100, "semi;colon", 'quote"d'])
def test_unsafe_request_ids_are_replaced(unsafe):
    response = client.get("/health", headers={"X-Request-ID": unsafe})

    assert response.headers["x-request-id"] != unsafe
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


# ---- completion line ------------------------------------------------------------------

def test_request_completed_has_route_status_latency_identity_and_outcome(caplog, stub_rag):
    caplog.set_level(logging.INFO)

    response = client.post("/talk", json={"question": "q"}, headers=bearer(employee_token()))

    [line] = completed(caplog)
    assert response.status_code == 200
    assert line["method"] == "POST" and line["route"] == "/talk" and line["status"] == 200
    assert line["duration_ms"] >= line["generation_ms"] >= 0
    assert line["sub"] == "alice" and line["roles"] == ["employee"]
    assert line["answer_outcome"] == "answered"
    assert line["request_id"] == response.headers["x-request-id"]


def test_all_lines_of_a_request_share_its_request_id(caplog, stub_rag):
    caplog.set_level(logging.DEBUG)

    response = client.post("/talk", json={"question": "q"}, headers=bearer("garbage"))

    ids = {l.get("request_id") for l in lines(caplog) if l.get("request_id")}
    assert ids == {response.headers["x-request-id"]}
    assert {"auth_failed", "request_completed"} <= {l["event"] for l in lines(caplog)}


def test_route_template_is_logged_not_the_raw_id(caplog, db):
    caplog.set_level(logging.INFO)
    conversation_id = str(uuid.uuid4())

    client.get(f"/conversations/{conversation_id}", headers=bearer(employee_token()))

    [line] = completed(caplog)
    assert line["route"] == "/conversations/{conversation_id}"
    assert line["status"] == 404


def test_stream_logged_once_after_last_byte_with_first_token_latency(caplog, stub_rag):
    caplog.set_level(logging.INFO)

    client.post("/ask/stream", json={"question": "q"}, headers=bearer(employee_token()))

    [line] = completed(caplog)
    assert line["route"] == "/ask/stream" and line["status"] == 200
    assert line["first_token_ms"] >= 0 and line["generation_ms"] >= 0
    assert line["answer_outcome"] == "answered"


def test_llm_unavailable_detail_is_logged_but_not_returned(caplog, monkeypatch, stub_rag):
    def unavailable(**_):
        raise LLMUnavailable("ollama 503: model loading")

    monkeypatch.setattr(rag, "generate_answer", unavailable)
    caplog.set_level(logging.INFO)

    response = client.post("/talk", json={"question": "q"}, headers=bearer(employee_token()))

    events = {l["event"]: l for l in lines(caplog)}
    assert response.status_code == 503 and "model loading" not in response.text
    assert events["llm_unavailable"]["level"] == "ERROR"
    assert events["llm_unavailable"]["detail"] == "ollama 503: model loading"
    assert events["request_completed"]["status"] == 503
    assert events["request_completed"]["answer_outcome"] == "llm_unavailable"


# ---- log safety ------------------------------------------------------------------------

def test_logs_never_contain_questions_answers_documents_or_tokens(caplog, stub_rag):
    caplog.set_level(logging.DEBUG)
    token = employee_token()

    client.post("/talk", json={"question": CANARY_QUESTION}, headers=bearer(token))
    client.post("/ask/stream", json={"question": CANARY_QUESTION}, headers=bearer(token))
    client.post("/talk", json={"question": CANARY_QUESTION},
                headers=bearer("CANARY-BAD-TOKEN.x.y"))

    output = "\n".join(FORMATTER.format(r) for r in caplog.records)
    for forbidden in ("CANARY-Q-7781", "CANARY-DOC-5531", "CANARY-A-9912",
                      "CANARY-BAD-TOKEN", token):
        assert forbidden not in output
    assert "auth_failed" in output  # the failure itself is recorded
