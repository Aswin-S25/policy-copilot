"""Liveness, readiness and startup warm-up.

/health        liveness: the process is up. No dependency checks, so a slow
               database never makes the supervisor restart a healthy API.
/health/ready  readiness: should this instance receive traffic?
               critical:      database, Ollama reachable with the model
                              pulled, embedding model loaded in-process
               informational: LLM resident in memory, Redis (ingestion only)

Warm-up runs in a background thread at startup: liveness answers at once,
readiness reports "warming_up" until the embedding model is loaded.
"""
import logging
import threading
import time
from contextlib import asynccontextmanager

import httpx
import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_infra_settings
from app.db import engine
from app.llm import LLM_MODEL, OLLAMA_HOST, LLMUnavailable, load_model
from ingest.embeddings import embed_text, embedding_model_loaded

logger = logging.getLogger("policy_copilot.health")
router = APIRouter(tags=["health"])

_settings = get_infra_settings()
PROBE_TIMEOUT_S = 2.0

_warmup = {"state": "pending"}  # pending | running | done | failed
_cache = {"at": 0.0, "result": None}
_cache_lock = threading.Lock()


# ---- checks: return normally if healthy, raise otherwise --------------------------

def _canonical(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


def _ollama_models(path: str) -> set[str]:
    response = httpx.get(f"{OLLAMA_HOST}{path}", timeout=PROBE_TIMEOUT_S)
    response.raise_for_status()
    return {
        _canonical(m.get("model") or m.get("name", ""))
        for m in response.json().get("models", [])
    }


def check_database() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def check_ollama() -> None:
    if _canonical(LLM_MODEL) not in _ollama_models("/api/tags"):
        raise RuntimeError(f"model {LLM_MODEL!r} is not pulled")


def check_embedding_model() -> None:
    if not embedding_model_loaded():
        raise RuntimeError("embedding model not loaded yet")


def check_llm_loaded() -> None:
    if _canonical(LLM_MODEL) not in _ollama_models("/api/ps"):
        raise RuntimeError("model not resident; the next request will load it")


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
    ("ollama", check_ollama, True),
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
