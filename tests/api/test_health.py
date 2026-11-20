import logging

import pytest
from fastapi.testclient import TestClient

import app.api.health as health
import app.rag.llm as llm
from app.main import app
from app.rag.llm import LLMUnavailable

client = TestClient(app)  # no "with": lifespan (warm-up) does not run


def ok():
    return None


def fail_with_secret():
    raise RuntimeError("secret-detail-xyz")


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setitem(health._cache, "result", None)
    monkeypatch.setitem(health._warmup, "state", "done")


def use_checks(monkeypatch, **results):
    """results: name -> (check function, critical)."""
    monkeypatch.setattr(
        health, "CHECKS",
        [(name, fn, critical) for name, (fn, critical) in results.items()],
    )


# ---- liveness / readiness --------------------------------------------------------------

def test_liveness_has_no_dependencies(monkeypatch):
    use_checks(monkeypatch, database=(fail_with_secret, True))

    assert client.get("/health").json() == {"status": "ok"}


def test_ready_when_all_critical_checks_pass(monkeypatch):
    use_checks(monkeypatch, database=(ok, True), redis=(fail_with_secret, False))

    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["redis"]["ok"] is False
    assert body["checks"]["redis"]["critical"] is False


def test_critical_failure_is_503_without_leaking_detail(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    use_checks(monkeypatch, database=(fail_with_secret, True), ollama=(ok, True))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["checks"]["database"]["ok"] is False
    assert "secret-detail-xyz" not in response.text
    assert any(r.getMessage() == "readiness_check_failed" for r in caplog.records)


def test_warming_up_while_startup_is_in_progress(monkeypatch):
    monkeypatch.setitem(health._warmup, "state", "running")
    use_checks(monkeypatch, embedding_model=(fail_with_secret, True))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "warming_up"


def test_results_are_cached_between_probes(monkeypatch):
    calls = []

    def counting():
        calls.append(1)

    use_checks(monkeypatch, database=(counting, True))

    client.get("/health/ready")
    client.get("/health/ready")

    assert len(calls) == 1


def test_database_check_against_real_test_database(db):
    health.check_database()  # raises if the database is unreachable


# ---- warm-up ------------------------------------------------------------------------------

def test_warm_up_loads_both_models(monkeypatch):
    loaded = []
    monkeypatch.setattr(health, "embed_text", lambda text: loaded.append("embedding"))
    monkeypatch.setattr(health, "load_model", lambda: loaded.append("llm"))

    health.warm_up()

    assert loaded == ["embedding", "llm"]
    assert health._warmup["state"] == "done"


def test_warm_up_survives_llm_outage(monkeypatch):
    def unavailable():
        raise LLMUnavailable("ConnectError")

    monkeypatch.setattr(health, "embed_text", lambda text: None)
    monkeypatch.setattr(health, "load_model", unavailable)

    health.warm_up()

    assert health._warmup["state"] == "done"


def test_warm_up_fails_if_embedding_model_cannot_load(monkeypatch):
    def broken(text):
        raise OSError("model files missing")

    monkeypatch.setattr(health, "embed_text", broken)

    health.warm_up()

    assert health._warmup["state"] == "failed"


# ---- LLM residency ---------------------------------------------------------------------------

class RecordingClient:
    def __init__(self):
        self.kwargs = []

    def chat(self, **kwargs):
        self.kwargs.append(kwargs)
        return {"message": {"content": "ok"}}

    def generate(self, **kwargs):
        self.kwargs.append(kwargs)
        return {}


def test_every_llm_call_extends_keep_alive(monkeypatch):
    fake = RecordingClient()
    monkeypatch.setattr(llm, "client", fake)
    monkeypatch.setattr(llm, "helper_client", fake)

    llm.generate_answer(system_prompt="s", user_prompt="u")
    llm.complete(system_prompt="s", user_prompt="u")
    llm.load_model()

    assert [k["keep_alive"] for k in fake.kwargs] == [llm.KEEP_ALIVE] * 3


def test_load_model_failure_becomes_llm_unavailable(monkeypatch):
    class Down:
        def generate(self, **_):
            raise ConnectionError("refused")

    monkeypatch.setattr(llm, "client", Down())

    with pytest.raises(LLMUnavailable):
        llm.load_model()
