"""OpenAI-compatible provider (Groq, Gemini, OpenRouter, Ollama /v1) through
a mocked transport: same contract as the Ollama path."""
import json

import httpx
import pytest

import app.rag.llm as llm


def make_client(handler):
    client = llm.OpenAICompatibleClient("https://llm.example/v1", "sk-test", timeout=5)
    client._http = httpx.Client(
        base_url="https://llm.example/v1",
        headers={"Authorization": "Bearer sk-test"},
        transport=httpx.MockTransport(handler),
    )
    return client


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDER", "openai")
    monkeypatch.setattr(llm, "RETRY_BACKOFF_S", 0)

    def use(handler):
        client = make_client(handler)
        monkeypatch.setattr(llm, "openai_client", client)
        monkeypatch.setattr(llm, "openai_helper_client", client)
        return client

    return use


def completion(content, **message):
    return httpx.Response(200, json={"choices": [{"message": {"content": content, **message}}]})


def sse(*events):
    lines = [f"data: {json.dumps(e)}\n\n" for e in events] + ["data: [DONE]\n\n"]
    return httpx.Response(200, text="".join(lines), headers={"Content-Type": "text/event-stream"})


def delta(text):
    return {"choices": [{"delta": {"content": text}}]}


def test_request_shape_and_answer(provider):
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return completion("24 days [Source 1].", reasoning="hidden chain of thought")

    provider(handler)
    answer = llm.generate_answer(system_prompt="sys", user_prompt="question")

    assert answer == "24 days [Source 1]."  # separate reasoning field ignored
    assert seen["path"] == "/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "question"},
    ]
    assert seen["body"]["temperature"] == 0.0 and seen["body"]["stream"] is False


def test_inline_thinking_is_removed(provider):
    provider(lambda request: completion("<think>let me reason</think>\n\nThe answer [Source 2]."))
    assert llm.complete(system_prompt="s", user_prompt="u") == "The answer [Source 2]."


def test_stream_yields_content_only(provider):
    provider(lambda request: sse(
        {"choices": [{"delta": {"role": "assistant"}}]},
        delta("<thi"), delta("nk>secret</th"), delta("ink>Leave is "),
        delta("24 days"), {"choices": []}, delta(" [Source 1]."),
    ))
    assert "".join(llm.stream_answer(system_prompt="s", user_prompt="u")) == "Leave is 24 days [Source 1]."


def test_rate_limit_is_retried_once_then_unavailable(provider):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": "rate limit reached"}})

    provider(handler)
    with pytest.raises(llm.LLMUnavailable, match="provider 429"):
        llm.generate_answer(system_prompt="s", user_prompt="u")
    assert len(calls) == 2


def test_bad_model_is_not_retried(provider):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(404, json={"error": {"message": "model not found"}})

    provider(handler)
    with pytest.raises(llm.LLMUnavailable):
        llm.generate_answer(system_prompt="s", user_prompt="u")
    assert len(calls) == 1


def test_stream_error_before_content_is_retried(provider):
    responses = [httpx.Response(503, text="busy"), sse(delta("ok [Source 1]."))]
    provider(lambda request: responses.pop(0))
    assert "".join(llm.stream_answer(system_prompt="s", user_prompt="u")) == "ok [Source 1]."


def test_error_event_mid_stream_becomes_unavailable(provider):
    provider(lambda request: sse(delta("partial"), {"error": {"message": "overloaded"}}))
    with pytest.raises(llm.LLMUnavailable):
        list(llm.stream_answer(system_prompt="s", user_prompt="u"))


def test_readiness_checks_the_model_is_offered(provider, monkeypatch):
    provider(lambda request: httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}]}))
    monkeypatch.setattr(llm, "LLM_MODEL", "openai/gpt-oss-120b")
    llm.check_model_available()  # no error
    llm.check_model_loaded()  # hosted: always fine

    monkeypatch.setattr(llm, "LLM_MODEL", "not-a-model")
    with pytest.raises(RuntimeError, match="not offered"):
        llm.check_model_available()


def test_load_model_is_a_no_op_for_hosted_providers(provider):
    provider(lambda request: pytest.fail("no request expected"))
    llm.load_model()


@pytest.mark.parametrize("tokens, expected", [
    (["plain text"], "plain text"),
    (["<think>a</think>b"], "b"),
    (["x<", "think>hidden</", "think>y"], "xy"),
    (["a < b and c </ d"], "a < b and c </ d"),  # lookalikes are kept
    (["<think>never closed"], ""),
])
def test_without_think(tokens, expected):
    assert "".join(llm.without_think(iter(tokens))) == expected
