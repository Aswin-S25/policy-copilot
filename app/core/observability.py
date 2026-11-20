"""Structured JSON logging with per-request context.

Every log line is one JSON object carrying the request_id of the request
that produced it. Each request ends with one "request_completed" line with
status, total latency, per-stage timings and turn facts.

Log-safety rule: log IDs, counts, roles, categories and timings only.
Never questions, answers, document content, tokens or secrets.
"""
import json
import logging
import re
import sys
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

REQUEST_ID_HEADER = b"x-request-id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
QUIET_ROUTES = {"/health", "/health/ready"}

# One mutable dict per request. Sync endpoints and SSE generators run in
# worker threads that receive a COPY of the context: setting a ContextVar
# there would not reach the middleware, but mutating this shared dict does.
_request: ContextVar[dict | None] = ContextVar("request_context", default=None)

_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {
    "message", "asctime", "color_message",
}

request_logger = logging.getLogger("policy_copilot.request")


# ---- request context ---------------------------------------------------------

@contextmanager
def request_context(request_id: str):
    ctx = {"request_id": request_id, "stages": {}, "fields": {}}
    token = _request.set(ctx)
    try:
        yield ctx
    finally:
        _request.reset(token)


def record(**fields) -> None:
    """Attach facts to the current request's completion line (no-op outside
    a request, e.g. in eval scripts)."""
    ctx = _request.get()
    if ctx is not None:
        ctx["fields"].update(fields)


def current_request_id() -> str | None:
    ctx = _request.get()
    return ctx["request_id"] if ctx else None


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


@contextmanager
def stage(name: str):
    """Time a pipeline stage; repeated stages accumulate."""
    start = time.perf_counter()
    try:
        yield
    finally:
        ctx = _request.get()
        if ctx is not None:
            key = f"{name}_ms"
            ctx["stages"][key] = round(ctx["stages"].get(key, 0.0) + ms_since(start), 1)


# ---- formatting ----------------------------------------------------------------

_base_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs):
    # Stamp request_id at creation time, in the thread that logged it.
    record_ = _base_factory(*args, **kwargs)
    ctx = _request.get()
    record_.request_id = ctx["request_id"] if ctx else None
    return record_


if logging.getLogRecordFactory() is not _record_factory:
    logging.setLogRecordFactory(_record_factory)


class JsonFormatter(logging.Formatter):
    def format(self, record_: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record_.created, timezone.utc)
                  .isoformat(timespec="milliseconds"),
            "level": record_.levelname,
            "logger": record_.name,
            "event": record_.getMessage(),
        }
        for key, value in record_.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_") and value is not None:
                entry[key] = value
        if record_.exc_info:
            entry["exc_type"] = record_.exc_info[0].__name__
            entry["exc"] = self.formatException(record_.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

    # One request_completed line per request replaces uvicorn's access log.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.propagate = True

    for noisy in ("httpx", "httpcore", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ---- middleware ------------------------------------------------------------------

def _log_completed(scope, ctx, status, start, *, failed=False, disconnected=False):
    route = getattr(scope.get("route"), "path", None) or "unmatched"
    level = (
        logging.ERROR if failed
        else logging.DEBUG if route in QUIET_ROUTES
        else logging.INFO
    )
    request_logger.log(
        level,
        "request_completed",
        exc_info=failed,
        extra={
            "method": scope["method"],
            "route": route,
            "status": status,
            "duration_ms": ms_since(start),
            "client_disconnected": disconnected or None,
            **ctx["stages"],
            **ctx["fields"],
        },
    )


class RequestContextMiddleware:
    """Pure ASGI middleware: request ID, context, and one completion line.

    Not BaseHTTPMiddleware: for SSE the completion line must be written
    when the last byte is sent, not when the endpoint returns.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers", [])).get(REQUEST_ID_HEADER, b"")
        incoming = incoming.decode("latin-1")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex

        start = time.perf_counter()
        state = {"status": None, "logged": False}

        with request_context(request_id) as ctx:

            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    state["status"] = message["status"]
                    message["headers"] = list(message.get("headers", [])) + [
                        (REQUEST_ID_HEADER, request_id.encode("latin-1"))
                    ]
                await send(message)
                if (
                    message["type"] == "http.response.body"
                    and not message.get("more_body", False)
                    and not state["logged"]
                ):
                    state["logged"] = True
                    _log_completed(scope, ctx, state["status"], start)

            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                if not state["logged"]:
                    state["logged"] = True
                    _log_completed(scope, ctx, 500, start, failed=True)
                raise
            finally:
                if not state["logged"]:  # body never completed: client went away
                    _log_completed(scope, ctx, state["status"], start, disconnected=True)
