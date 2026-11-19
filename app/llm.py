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
import time
from collections.abc import Iterator

import httpx
from ollama import Client, ResponseError

from app.config import get_infra_settings

_settings = get_infra_settings()

OLLAMA_HOST = _settings.ollama_host
LLM_MODEL = _settings.llm_model
GENERATION_TIMEOUT_S = _settings.llm_timeout_s

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
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = chat_client.chat(**kwargs)
            return response["message"]["content"]
        except LLM_ERRORS as exc:
            if attempt < MAX_ATTEMPTS and _retryable(exc):
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
    )


def stream_answer(system_prompt: str, user_prompt: str) -> Iterator[str]:
    """Stream answer content with the same settings as generate_answer().

    Thinking arrives in message["thinking"] and is never yielded. httpx
    timeouts apply per read and thinking streams continuously, so a total
    deadline is enforced here as well.
    """
    yielded = False

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
            if not yielded and attempt < MAX_ATTEMPTS and _retryable(exc):
                time.sleep(RETRY_BACKOFF_S * attempt)
                continue
            raise LLMUnavailable(_describe(exc)) from exc
        finally:
            if stream is not None and hasattr(stream, "close"):
                stream.close()  # release the HTTP connection on any exit
