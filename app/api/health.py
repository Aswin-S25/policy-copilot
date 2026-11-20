"""Liveness, readiness and startup warm-up.

/health        liveness: the process is up. No dependency checks, so a slow
               database never makes the supervisor restart a healthy API.
/health/ready  readiness: should this instance receive traffic?
               critical:      database, LLM provider reachable and serving the
                              model, embedding model loaded in-process
               informational: LLM resident in memory (Ollama only), Redis
                              (ingestion and shared rate limits only)

Warm-up runs in a background thread at startup: liveness answers at once,
readiness reports "warming_up" until the embedding model is loaded.
"""
import logging
import threading
import time
from contextlib import asynccontextmanager

import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_infra_settings
from app.core.db import engine
from app.rag.llm import LLMUnavailable, check_model_available, check_model_loaded, load_model
from ingest.embeddings import embed_text, embedding_model_loaded

logger = logging.getLogger("policy_copilot.health")
router = APIRouter(tags=["health"])

_settings = get_infra_settings()
PROBE_TIMEOUT_S = 2.0

_warmup = {"state": "pending"}  # pending | running | done | failed
_cache = {"at": 0.0, "result": None}
_cache_lock = threading.Lock()


# ---- checks: return normally if healthy, raise otherwise --------------------------

def check_database() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def check_llm() -> None:
    check_model_available()


def check_embedding_model() -> None:
    if not embedding_model_loaded():
        raise RuntimeError("embedding model not loaded yet")


def check_llm_loaded() -> None:
    check_model_loaded()


def check_redis() -> None:
    client = redis.Redis.from_url(
        _settings.celery_broker_url,
        socket_connect_timeout=PROBE_TIMEOUT_S,
        socket_timeout=PROBE_TIMEOUT_S,
    )
    try:
        client.ping()
    finally:
        client.close()


# (name, check, critical)
CHECKS = [
    ("database", check_database, True),
    ("llm", check_llm, True),
    ("embedding_model", check_embedding_model, True),
    ("llm_loaded", check_llm_loaded, False),
    ("redis", check_redis, False),
]


def _run(name, check, critical) -> dict:
    start = time.perf_counter()
    try:
        check()
        ok = True
    except Exception as exc:
        ok = False
        # Detail goes to the log only; the endpoint is unauthenticated.
        logger.log(
            logging.WARNING if critical else logging.DEBUG,
            "readiness_check_failed",
            extra={"check": name, "detail": f"{type(exc).__name__}: {exc}"},
        )
    return {
        "ok": ok,
        "critical": critical,
        "ms": round((time.perf_counter() - start) * 1000, 1),
    }


def readiness() -> tuple[int, dict]:
    # One probe at a time, results reused briefly: many simultaneous probes
    # must not become many database/Ollama round trips.
    with _cache_lock:
        now = time.monotonic()
        cached = _cache["result"]
        if cached is not None and now - _cache["at"] < _settings.readiness_cache_s:
            return cached

        checks = {name: _run(name, check, critical) for name, check, critical in CHECKS}
        critical_ok = all(c["ok"] for c in checks.values() if c["critical"])

        if critical_ok:
            status = "ready"
        elif _warmup["state"] in ("pending", "running"):
            status = "warming_up"
        else:
            status = "unavailable"

        result = (
            200 if critical_ok else 503,
            {"status": status, "warmup": _warmup["state"], "checks": checks},
        )
        _cache.update(at=now, result=result)
        return result


# ---- endpoints -------------------------------------------------------------------------

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/ready")
def ready():
    status_code, body = readiness()
    return JSONResponse(status_code=status_code, content=body)


# ---- warm-up -----------------------------------------------------------------------------

def warm_up() -> None:
    _warmup["state"] = "running"
    timings = {}

    try:
        start = time.perf_counter()
        embed_text("warm-up")
        timings["embedding_ms"] = round((time.perf_counter() - start) * 1000, 1)
    except Exception:
        logger.exception("warmup_failed", extra={"step": "embedding"})
        _warmup["state"] = "failed"
        return

    try:
        start = time.perf_counter()
        load_model()
        timings["llm_ms"] = round((time.perf_counter() - start) * 1000, 1)
    except LLMUnavailable as exc:
        # Not fatal: the model loads on the first request instead.
        logger.warning("warmup_llm_skipped", extra={"detail": str(exc)})

    _warmup["state"] = "done"
    _cache["result"] = None  # let readiness reflect the new state at once
    logger.info("warmup_completed", extra=timings)


@asynccontextmanager
async def lifespan(app):
    if _settings.warmup_on_startup:
        threading.Thread(target=warm_up, name="warmup", daemon=True).start()
    yield
