"""LLM access with bounded time and explicit failure.

Two providers behind the same functions (POLICY_LLM_PROVIDER):
  ollama  local Ollama through its Python client (default)
  openai  any OpenAI-compatible /chat/completions API (Groq, Gemini,
          OpenRouter, Ollama's /v1), through httpx; for hosted deployment

Every function returns model output or raises LLMUnavailable; callers never
see raw httpx/ollama exceptions. Model reasoning ("thinking") is never
returned as answer text, whichever way the provider delivers it.

Retry policy: one retry with short backoff, only before any output exists:
  * connection refused / connect timeout   (server down or restarting)
  * HTTP 429 / 500 / 502 / 503 / 504        (overloaded, model loading)
No retry for:
  * read timeouts: the full time budget was already spent
  * other 4xx, e.g. 404 "model not found": configuration errors
  * failures after streaming started: the client already shows tokens
"""
import json
import logging
import re
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import httpx
from ollama import Client, ResponseError

from app.core.config import get_infra_settings
from app.core.observability import stage

logger = logging.getLogger("policy_copilot.llm")

_settings = get_infra_settings()

PROVIDER = _settings.llm_provider
OLLAMA_HOST = _settings.ollama_host
LLM_MODEL = _settings.llm_model
GENERATION_TIMEOUT_S = _settings.llm_timeout_s
KEEP_ALIVE = _settings.llm_keep_alive
QUEUE_TIMEOUT_S = _settings.llm_queue_timeout_s
MAX_CONCURRENCY = _settings.llm_max_concurrency

# Bounded, visible queue in front of Ollama (per process).
_slots = threading.BoundedSemaphore(MAX_CONCURRENCY)

MAX_ATTEMPTS = 2
RETRY_BACKOFF_S = 1.0
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

UNAVAILABLE_MESSAGE = (
    "The answer service is temporarily unavailable. Please try again shortly."
)

# Answers may legitimately take a while; helper tasks get a shorter budget.
client = Client(host=OLLAMA_HOST, timeout=_settings.llm_timeout_s)
helper_client = Client(host=OLLAMA_HOST, timeout=_settings.llm_helper_timeout_s)

# ConnectionError: ollama's wrapper for refused connections.
# httpx.TransportError: timeouts and dropped connections (not wrapped by ollama).
# httpx.HTTPStatusError: error statuses from the OpenAI-compatible provider.
LLM_ERRORS = (ConnectionError, httpx.TransportError, httpx.HTTPStatusError, ResponseError)


class LLMUnavailable(Exception):
    """The model produced no usable output. The detail is for logs only."""


class LLMBusy(LLMUnavailable):
    """Every generation slot stayed busy for the whole queue timeout."""


@contextmanager
def _generation_slot():
    with stage("llm_queue"):
        acquired = _slots.acquire(timeout=QUEUE_TIMEOUT_S)
    if not acquired:
        logger.warning("llm_busy", extra={
            "max_concurrency": MAX_CONCURRENCY, "queue_timeout_s": QUEUE_TIMEOUT_S,
        })
        raise LLMBusy(f"no generation slot within {QUEUE_TIMEOUT_S}s")
    try:
        yield
    finally:
        _slots.release()


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, httpx.ConnectError, httpx.ConnectTimeout)):
        return True
    if isinstance(exc, ResponseError):
        return exc.status_code in RETRYABLE_STATUS
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return False


def _describe(exc: Exception) -> str:
    if isinstance(exc, ResponseError):
        return f"ollama {exc.status_code}: {exc.error}"
    if isinstance(exc, httpx.HTTPStatusError):
        # Provider error bodies explain quota/model problems; logs only.
        return f"provider {exc.response.status_code}: {exc.response.text[:300]}"
    return f"{type(exc).__name__}: {exc}"


def _messages(system_prompt: str, user_prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _with_retry(call: Callable[[], str], model: str) -> str:
    """One generation slot; one retry for transient failures (see module doc)."""
    with _generation_slot():
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return call()
            except LLM_ERRORS as exc:
                retry = attempt < MAX_ATTEMPTS and _retryable(exc)
                logger.warning("llm_call_failed", extra={
                    "model": model, "attempt": attempt,
                    "will_retry": retry, "detail": _describe(exc),
                })
                if retry:
                    time.sleep(RETRY_BACKOFF_S * attempt)
                    continue
                raise LLMUnavailable(_describe(exc)) from exc
    raise AssertionError("unreachable")


def _chat(chat_client: Client, **kwargs) -> str:
    return _with_retry(lambda: chat_client.chat(**kwargs)["message"]["content"], kwargs.get("model"))


# ---- OpenAI-compatible provider ------------------------------------------------------

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_OPEN, _THINK_CLOSE = "<think>", "</think>"


def strip_think(text: str) -> str:
    """Some models (Qwen3 on some providers) put reasoning inline in <think>."""
    return _THINK_BLOCK.sub("", text).strip()


def _partial_tag(text: str, tag: str) -> int:
    """Length of the longest end of `text` that could begin `tag`."""
    for size in range(min(len(tag) - 1, len(text)), 0, -1):
        if tag.startswith(text[-size:]):
            return size
    return 0


def without_think(tokens: Iterator[str]) -> Iterator[str]:
    """Streams text with <think>...</think> spans removed, even when the
    tags are split across tokens."""
    buffer, inside = "", False
    for token in tokens:
        buffer += token
        while buffer:
            if inside:
                end = buffer.find(_THINK_CLOSE)
                if end == -1:
                    buffer = buffer[len(buffer) - _partial_tag(buffer, _THINK_CLOSE):]
                    break
                buffer, inside = buffer[end + len(_THINK_CLOSE):], False
            else:
                start = buffer.find(_THINK_OPEN)
                if start == -1:
                    keep = _partial_tag(buffer, _THINK_OPEN)
                    if len(buffer) > keep:
                        yield buffer[:len(buffer) - keep]
                        buffer = buffer[len(buffer) - keep:]
                    break
                if start:
                    yield buffer[:start]
                buffer, inside = buffer[start + len(_THINK_OPEN):], True
    if buffer and not inside:
        yield buffer


class OpenAICompatibleClient:
    """Minimal /chat/completions client; no SDK. The API key is only ever
    sent as a header and never logged."""

    def __init__(self, base_url: str, api_key: str | None, timeout: float):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)

    def _body(self, system_prompt: str, user_prompt: str, stream: bool) -> dict:
        body = {
            "model": LLM_MODEL,
            "messages": _messages(system_prompt, user_prompt),
            "temperature": 0.0,
            "stream": stream,
        }
        if _settings.llm_reasoning_effort:
            body["reasoning_effort"] = _settings.llm_reasoning_effort
        return body

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._http.post("/chat/completions", json=self._body(system_prompt, user_prompt, False))
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        # Separate reasoning fields ("reasoning", "reasoning_content") are ignored.
        return strip_think(message.get("content") or "")

    @contextmanager
    def stream(self, system_prompt: str, user_prompt: str) -> Iterator[Iterator[str]]:
        body = self._body(system_prompt, user_prompt, True)
        with self._http.stream("POST", "/chat/completions", json=body) as response:
            if response.status_code >= 400:
                response.read()
                response.raise_for_status()
            yield without_think(self._content(response.iter_lines()))

    @staticmethod
    def _content(lines: Iterator[str]) -> Iterator[str]:
        for line in lines:
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            event = json.loads(data)
            if event.get("error"):
                raise LLMUnavailable(f"provider stream error: {str(event['error'])[:300]}")
            for choice in event.get("choices") or []:
                content = (choice.get("delta") or {}).get("content")
                if content:
                    yield content

    def model_ids(self) -> set[str]:
        response = self._http.get("/models", timeout=5.0)
        response.raise_for_status()
        return {model["id"] for model in response.json().get("data", [])}


def _openai_client(timeout: float) -> OpenAICompatibleClient | None:
    if PROVIDER != "openai":
        return None
    key = _settings.llm_api_key.get_secret_value() if _settings.llm_api_key else None
    return OpenAICompatibleClient(_settings.llm_base_url, key, timeout)


openai_client = _openai_client(_settings.llm_timeout_s)
openai_helper_client = _openai_client(_settings.llm_helper_timeout_s)


# ---- entry points -----------------------------------------------------------------

def generate_answer(system_prompt: str, user_prompt: str) -> str:
    if PROVIDER == "openai":
        return _with_retry(lambda: openai_client.complete(system_prompt, user_prompt), LLM_MODEL)
    return _chat(
        client,
        model=LLM_MODEL,
        messages=_messages(system_prompt, user_prompt),
        options={"temperature": 0.0},
        think=True,
        keep_alive=KEEP_ALIVE,
    )


def complete(
    system_prompt: str,
    user_prompt: str,
    *,
    think: bool = False,
) -> str:
    """Short helper completions such as query rewriting (shorter timeout)."""
    if PROVIDER == "openai":
        return _with_retry(lambda: openai_helper_client.complete(system_prompt, user_prompt), LLM_MODEL)
    return _chat(
        helper_client,
        model=LLM_MODEL,
        messages=_messages(system_prompt, user_prompt),
        options={"temperature": 0.0},
        think=think,
        keep_alive=KEEP_ALIVE,
    )


def stream_answer(system_prompt: str, user_prompt: str) -> Iterator[str]:
    """Stream answer content with the same settings as generate_answer().

    Thinking arrives in message["thinking"] and is never yielded. httpx
    timeouts apply per read and thinking streams continuously, so a total
    deadline is enforced here as well.
    """
    open_stream = (
        (lambda: openai_client.stream(system_prompt, user_prompt))
        if PROVIDER == "openai"
        else (lambda: _ollama_stream(system_prompt, user_prompt))
    )
    yield from _stream_with_retry(open_stream)


@contextmanager
def _ollama_stream(system_prompt: str, user_prompt: str) -> Iterator[Iterator[str]]:
    stream = client.chat(
        model=LLM_MODEL,
        messages=_messages(system_prompt, user_prompt),
        options={"temperature": 0.0},
        think=True,
        stream=True,
        keep_alive=KEEP_ALIVE,
    )
    try:
        yield (chunk["message"]["content"] for chunk in stream)
    finally:
        if hasattr(stream, "close"):
            stream.close()  # release the HTTP connection on any exit


def _stream_with_retry(
    open_stream: Callable[[], AbstractContextManager[Iterator[str]]],
) -> Iterator[str]:
    yielded = False

    # A generator: the slot is taken at the first next() and released when
    # the stream finishes, fails, or is closed early (client disconnect).
    with _generation_slot():
        for attempt in range(1, MAX_ATTEMPTS + 1):
            deadline = time.monotonic() + GENERATION_TIMEOUT_S
            try:
                with open_stream() as contents:
                    for content in contents:
                        if time.monotonic() > deadline:
                            raise LLMUnavailable(
                                f"generation exceeded {GENERATION_TIMEOUT_S}s"
                            )
                        if content:
                            yielded = True
                            yield content
                return
            except LLM_ERRORS as exc:
                retry = not yielded and attempt < MAX_ATTEMPTS and _retryable(exc)
                logger.warning("llm_call_failed", extra={
                    "model": LLM_MODEL, "attempt": attempt, "streaming": True,
                    "after_output": yielded, "will_retry": retry,
                    "detail": _describe(exc),
                })
                if retry:
                    time.sleep(RETRY_BACKOFF_S * attempt)
                    continue
                raise LLMUnavailable(_describe(exc)) from exc


def load_model() -> None:
    """Ask Ollama to load the model into memory now (empty prompt), so the
    first user request does not pay the load time. Hosted providers keep
    their models loaded: nothing to do."""
    if PROVIDER == "openai":
        return
    try:
        client.generate(model=LLM_MODEL, prompt="", keep_alive=KEEP_ALIVE)
    except LLM_ERRORS as exc:
        raise LLMUnavailable(_describe(exc)) from exc


# ---- readiness probes (app/api/health.py) -----------------------------------------

def _canonical(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


def _ollama_models(path: str) -> set[str]:
    response = httpx.get(f"{OLLAMA_HOST}{path}", timeout=2.0)
    response.raise_for_status()
    return {
        _canonical(m.get("model") or m.get("name", ""))
        for m in response.json().get("models", [])
    }


def check_model_available() -> None:
    """Raises unless the provider is reachable and serves the model."""
    if PROVIDER == "openai":
        if LLM_MODEL not in openai_helper_client.model_ids():
            raise RuntimeError(f"model {LLM_MODEL!r} is not offered by the provider")
        return
    if _canonical(LLM_MODEL) not in _ollama_models("/api/tags"):
        raise RuntimeError(f"model {LLM_MODEL!r} is not pulled")


def check_model_loaded() -> None:
    """Ollama only: is the model resident in memory (next request is fast)?"""
    if PROVIDER == "openai":
        return
    if _canonical(LLM_MODEL) not in _ollama_models("/api/ps"):
        raise RuntimeError("model not resident; the next request will load it")
