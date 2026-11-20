import httpx
import pytest
from ollama import ResponseError

import app.rag.llm as llm


class FakeClient:
    """Plays a script: exceptions are raised, other values returned."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def reply(text):
    return {"message": {"content": text}}


def stream_of(*items):
    """Fake stream: strings become chunks, exceptions are raised mid-stream."""
    def generate():
        for item in items:
            if isinstance(item, Exception):
                raise item
            yield {"message": {"content": item}}
    return generate()


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_BACKOFF_S", 0)


def use(monkeypatch, fake):
    monkeypatch.setattr(llm, "client", fake)
    monkeypatch.setattr(llm, "helper_client", fake)
    return fake


def ask():
    return llm.generate_answer(system_prompt="s", user_prompt="u")


# ---- blocking calls -----------------------------------------------------------

def test_connection_error_is_retried_once(monkeypatch):
    fake = use(monkeypatch, FakeClient(ConnectionError("down"), reply("ok")))

    assert ask() == "ok"
    assert fake.calls == 2


def test_persistent_server_error_raises_after_one_retry(monkeypatch):
    fake = use(monkeypatch, FakeClient(ResponseError("busy", 503), ResponseError("busy", 503)))

    with pytest.raises(llm.LLMUnavailable):
        ask()
    assert fake.calls == 2


def test_model_not_found_is_not_retried(monkeypatch):
    fake = use(monkeypatch, FakeClient(ResponseError("model 'x' not found", 404)))

    with pytest.raises(llm.LLMUnavailable, match="404"):
        ask()
    assert fake.calls == 1


def test_read_timeout_is_not_retried(monkeypatch):
    fake = use(monkeypatch, FakeClient(httpx.ReadTimeout("slow")))

    with pytest.raises(llm.LLMUnavailable):
        llm.complete(system_prompt="s", user_prompt="u")
    assert fake.calls == 1


def test_dropped_connection_becomes_llm_unavailable(monkeypatch):
    use(monkeypatch, FakeClient(httpx.RemoteProtocolError("server disconnected")))

    with pytest.raises(llm.LLMUnavailable):
        ask()


# ---- streaming ----------------------------------------------------------------------

def test_stream_retries_if_failure_happens_before_any_content(monkeypatch):
    # "" is a thinking chunk: no answer content has been shown yet.
    fake = use(monkeypatch, FakeClient(
        stream_of("", ConnectionError("restart")),
        stream_of("Hello", " world"),
    ))

    assert list(llm.stream_answer(system_prompt="s", user_prompt="u")) == ["Hello", " world"]
    assert fake.calls == 2


def test_stream_failure_after_content_is_not_retried(monkeypatch):
    fake = use(monkeypatch, FakeClient(stream_of("Hello", httpx.ReadTimeout("stalled"))))
    tokens = []

    with pytest.raises(llm.LLMUnavailable):
        for token in llm.stream_answer(system_prompt="s", user_prompt="u"):
            tokens.append(token)

    assert tokens == ["Hello"]
    assert fake.calls == 1


def test_stream_enforces_total_deadline(monkeypatch):
    monkeypatch.setattr(llm, "GENERATION_TIMEOUT_S", -1)
    use(monkeypatch, FakeClient(stream_of("a", "b")))

    with pytest.raises(llm.LLMUnavailable, match="exceeded"):
        list(llm.stream_answer(system_prompt="s", user_prompt="u"))
