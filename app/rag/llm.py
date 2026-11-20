"""Ollama access with bounded time and explicit failure.

Every function returns model output or raises LLMUnavailable; callers never
see raw httpx/ollama exceptions.

Retry policy: one retry with short backoff, only before any output exists:
  * connection refused / connect timeout   (server down or restarting)
  * HTTP 429 / 500 / 502 / 503 / 504        (overloaded, model loading)
No retry for:
  * read timeouts: the full time budget was already spent
  * other 4xx, e.g. 404 "model not found": configuration errors
  * failures after streaming started: the client already shows tokens
"""
import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
from ollama import Client, ResponseError

from app.core.config import get_infra_settings
from app.core.observability import stage

logger = logging.getLogger("policy_copilot.llm")

_settings = get_infra_settings()

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
LLM_ERRORS = (ConnectionError, httpx.TransportError, ResponseError)


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
    return False


def _describe(exc: Exception) -> str:
    if isinstance(exc, ResponseError):
        return f"ollama {exc.status_code}: {exc.error}"
    return f"{type(exc).__name__}: {exc}"


def _messages(system_prompt: str, user_prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _chat(chat_client: Client, **kwargs) -> str:
    with _generation_slot():
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = chat_client.chat(**kwargs)
                return response["message"]["content"]
            except LLM_ERRORS as exc:
                retry = attempt < MAX_ATTEMPTS and _retryable(exc)
                logger.warning("llm_call_failed", extra={
                    "model": kwargs.get("model"), "attempt": attempt,
                    "will_retry": retry, "detail": _describe(exc),
                })
                if retry:
                    time.sleep(RETRY_BACKOFF_S * attempt)
                    continue
                raise LLMUnavailable(_describe(exc)) from exc
    raise AssertionError("unreachable")


def generate_answer(system_prompt: str, user_prompt: str) -> str:
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
    yielded = False

    # A generator: the slot is taken at the first next() and released when
    # the stream finishes, fails, or is closed early (client disconnect).
    with _generation_slot():
        for attempt in range(1, MAX_ATTEMPTS + 1):
            deadline = time.monotonic() + GENERATION_TIMEOUT_S
            stream = None
            try:
                stream = client.chat(
                    model=LLM_MODEL,
                    messages=_messages(system_prompt, user_prompt),
                    options={"temperature": 0.0},
                    think=True,
                    stream=True,
                    keep_alive=KEEP_ALIVE,
                )
                for chunk in stream:
                    if time.monotonic() > deadline:
                        raise LLMUnavailable(
                            f"generation exceeded {GENERATION_TIMEOUT_S}s"
                        )
                    content = chunk["message"]["content"]
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
            finally:
                if stream is not None and hasattr(stream, "close"):
                    stream.close()  # release the HTTP connection on any exit


def load_model() -> None:
    """Ask Ollama to load the model into memory now (empty prompt), so the
    first user request does not pay the load time."""
    try:
        client.generate(model=LLM_MODEL, prompt="", keep_alive=KEEP_ALIVE)
    except LLM_ERRORS as exc:
        raise LLMUnavailable(_describe(exc)) from exc
