import logging
import threading
import uuid

import pytest
import redis
from fastapi.testclient import TestClient

import app.api as api
import app.llm as llm
import app.rag as rag
import app.rate_limit as rate_limit
from app.api import app
from app.config import get_infra_settings
from app.llm import LLMBusy, LLMUnavailable
from app.rate_limit import MemoryBackend, RateLimiter, RedisBackend
from app.retrieval import RetrievedChunk
from app.security import create_access_token

client = TestClient(app)


def bearer(sub, roles=("employee",)):
    return {"Authorization": f"Bearer {create_access_token(sub, list(roles))}"}


@pytest.fixture
def limits(monkeypatch):
    def use(**limits):
        limiter = RateLimiter(MemoryBackend(), limits={"llm": 99, "search": 99, **limits})
        monkeypatch.setattr(rate_limit, "limiter", limiter)
        return limiter
    return use


@pytest.fixture
def stub_rag(monkeypatch):
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), document_title="H",
        section_path="S", content="24 days of leave.", chunk_index=0, score=0.03,
    )
    monkeypatch.setattr(rag, "search_policies", lambda **_: [chunk])
    monkeypatch.setattr(api, "search_policies", lambda **_: [chunk])
    monkeypatch.setattr(rag, "generate_answer", lambda **_: "24 days [Source 1].")


# ---- limiter logic ----------------------------------------------------------------

def test_memory_backend_counts_per_window_and_resets():
    backend = MemoryBackend()

    assert [backend.hit("k", 1) for _ in range(3)] == [1, 2, 3]
    assert backend.hit("k", 2) == 1  # new window starts from zero


def test_allows_up_to_limit_then_denies_per_subject_and_scope():
    limiter = RateLimiter(MemoryBackend(), limits={"llm": 2, "search": 5})

    decisions = [limiter.check("llm", "alice") for _ in range(3)]

    assert [d.allowed for d in decisions] == [True, True, False]
    assert [d.remaining for d in decisions] == [1, 0, 0]
    assert limiter.check("llm", "bob").allowed        # other user unaffected
    assert limiter.check("search", "alice").allowed   # other scope unaffected


def test_disabled_limiter_always_allows():
    limiter = RateLimiter(MemoryBackend(), limits={"llm": 1}, enabled=False)

    assert all(limiter.check("llm", "alice").allowed for _ in range(5))


def test_fails_open_when_backend_unreachable(caplog):
    class DownBackend:
        def hit(self, key, window):
            raise redis.ConnectionError("refused")

    caplog.set_level(logging.WARNING)
    limiter = RateLimiter(DownBackend(), limits={"llm": 1})

    assert limiter.check("llm", "alice").allowed
    assert any(r.getMessage() == "rate_limit_unavailable" for r in caplog.records)


def test_redis_backend_counts_and_sets_expiry():
    backend = RedisBackend(get_infra_settings().rate_limit_redis_url)
    try:
        backend._client.ping()
    except redis.RedisError:
        pytest.skip("Redis not available")

    key = f"test:{uuid.uuid4()}"
    try:
        assert backend.hit(key, 1) == 1
        assert backend.hit(key, 1) == 2
        assert 0 < backend._client.ttl(f"ratelimit:{key}:1") <= 120
    finally:
        backend._client.delete(f"ratelimit:{key}:1")


# ---- API ------------------------------------------------------------------------------

def test_third_llm_request_gets_429_with_headers(limits, stub_rag):
    limits(llm=2)
    headers = bearer("alice")

    codes = [client.post("/talk", json={"question": "q"}, headers=headers).status_code
             for _ in range(2)]
    denied = client.post("/talk", json={"question": "q"}, headers=headers)

    assert codes == [200, 200]
    assert denied.status_code == 429
    assert denied.headers["RateLimit-Limit"] == "2"
    assert 1 <= int(denied.headers["Retry-After"]) <= 60
    assert client.post("/talk", json={"question": "q"},
                       headers=bearer("bob")).status_code == 200


def test_search_and_llm_budgets_are_separate(limits, stub_rag):
    limits(llm=1, search=99)
    headers = bearer("alice")

    client.post("/talk", json={"question": "q"}, headers=headers)

    assert client.post("/talk", json={"question": "q"}, headers=headers).status_code == 429
    assert client.post("/search", json={"query": "q"}, headers=headers).status_code == 200


def test_unauthenticated_requests_get_401_and_use_no_quota(limits, stub_rag):
    limiter = limits(llm=1)

    assert client.post("/talk", json={"question": "q"}).status_code == 401
    assert limiter.check("llm", "alice").allowed  # quota untouched


def test_conversation_turns_use_llm_budget(limits):
    limits(llm=0)
    url = f"/conversations/{uuid.uuid4()}/messages"

    assert client.post(url, json={"question": "q"}, headers=bearer("alice")).status_code == 429
    assert client.post(url + "/stream", json={"question": "q"},
                       headers=bearer("alice")).status_code == 429


# ---- LLM concurrency cap -----------------------------------------------------------------

class InstantClient:
    def chat(self, **kwargs):
        if kwargs.get("stream"):
            return iter([{"message": {"content": "a"}}, {"message": {"content": "b"}}])
        return {"message": {"content": "ok"}}


@pytest.fixture
def one_slot(monkeypatch):
    monkeypatch.setattr(llm, "_slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(llm, "QUEUE_TIMEOUT_S", 0.05)
    monkeypatch.setattr(llm, "client", InstantClient())
    monkeypatch.setattr(llm, "helper_client", InstantClient())


def test_busy_slot_raises_llm_busy_which_is_llm_unavailable(one_slot):
    llm._slots.acquire()  # someone else is generating
    try:
        with pytest.raises(LLMBusy):
            llm.generate_answer(system_prompt="s", user_prompt="u")
    finally:
        llm._slots.release()

    assert issubclass(LLMBusy, LLMUnavailable)


def test_slot_is_released_after_each_call(one_slot):
    for _ in range(3):
        assert llm.generate_answer(system_prompt="s", user_prompt="u") == "ok"


def test_stream_releases_slot_when_finished_or_abandoned(one_slot):
    assert list(llm.stream_answer(system_prompt="s", user_prompt="u")) == ["a", "b"]

    abandoned = llm.stream_answer(system_prompt="s", user_prompt="u")
    next(abandoned)    # slot taken
    abandoned.close()  # client disconnected

    assert llm.generate_answer(system_prompt="s", user_prompt="u") == "ok"


def test_busy_llm_returns_503(limits, stub_rag, monkeypatch):
    limits()

    def busy(**_):
        raise LLMBusy("no generation slot within 10s")

    monkeypatch.setattr(rag, "generate_answer", busy)

    response = client.post("/talk", json={"question": "q"}, headers=bearer("alice"))

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "10"
