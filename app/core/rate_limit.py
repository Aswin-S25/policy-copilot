"""Per-user rate limits.

Fixed one-minute windows keyed by the authenticated subject:
  llm     answer-generating endpoints  (POLICY_RATE_LIMIT_LLM_PER_MINUTE)
  search  retrieval-only endpoint      (POLICY_RATE_LIMIT_SEARCH_PER_MINUTE)

Backends: Redis (shared by all API processes) or in-memory (one process,
tests). If Redis is unreachable the limiter FAILS OPEN and logs a warning:
rate limiting protects capacity; it is not an authorization control, and a
Redis outage must not take question answering down.

Fixed windows allow up to 2x the limit across a window boundary, which is
acceptable for abuse protection.
"""
import logging
import threading
import time
from dataclasses import dataclass

import redis
from fastapi import Depends, HTTPException, status

from app.core.config import get_infra_settings
from app.core.observability import record
from app.core.security import Principal, get_current_principal

logger = logging.getLogger("policy_copilot.rate_limit")

WINDOW_S = 60


@dataclass
class Decision:
    allowed: bool
    limit: int
    remaining: int
    reset_s: int


class MemoryBackend:
    """Single-process counter; old windows are dropped at each boundary."""

    def __init__(self):
        self._lock = threading.Lock()
        self._window = None
        self._counts: dict[str, int] = {}

    def hit(self, key: str, window: int) -> int:
        with self._lock:
            if window != self._window:
                self._counts.clear()
                self._window = window
            self._counts[key] = self._counts.get(key, 0) + 1
            return self._counts[key]


class RedisBackend:
    def __init__(self, url: str):
        # Short timeouts: a slow Redis must not slow every request.
        self._client = redis.Redis.from_url(
            url, socket_connect_timeout=0.5, socket_timeout=0.5
        )

    def hit(self, key: str, window: int) -> int:
        redis_key = f"ratelimit:{key}:{window}"
        pipe = self._client.pipeline()  # MULTI/EXEC: increment and expiry together
        pipe.incr(redis_key)
        pipe.expire(redis_key, WINDOW_S * 2)
        count, _ = pipe.execute()
        return int(count)


class RateLimiter:
    def __init__(self, backend, limits: dict[str, int], enabled: bool = True):
        self.backend = backend
        self.limits = limits
        self.enabled = enabled

    def check(self, scope: str, subject: str) -> Decision:
        limit = self.limits[scope]
        now = time.time()
        window = int(now // WINDOW_S)
        reset_s = WINDOW_S - int(now % WINDOW_S)

        if not self.enabled:
            return Decision(True, limit, limit, reset_s)

        try:
            count = self.backend.hit(f"{scope}:{subject}", window)
        except redis.RedisError as exc:
            logger.warning("rate_limit_unavailable", extra={
                "detail": f"{type(exc).__name__}: {exc}",
            })
            return Decision(True, limit, limit, reset_s)  # fail open

        return Decision(count <= limit, limit, max(0, limit - count), reset_s)


def build_limiter() -> RateLimiter:
    settings = get_infra_settings()
    backend = (
        RedisBackend(settings.rate_limit_redis_url)
        if settings.rate_limit_backend == "redis"
        else MemoryBackend()
    )
    return RateLimiter(
        backend,
        limits={
            "llm": settings.rate_limit_llm_per_minute,
            "search": settings.rate_limit_search_per_minute,
            "login_user": settings.rate_limit_login_per_minute,
            "login_ip": settings.rate_limit_login_ip_per_minute,
        },
        enabled=settings.rate_limit_enabled,
    )


limiter = build_limiter()


def rate_limited(scope: str):
    """Dependency: authenticate first (401 before 429), then count."""

    def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        decision = limiter.check(scope, principal.subject)
        if not decision.allowed:
            logger.warning("rate_limited", extra={"scope": scope, "limit": decision.limit})
            record(rate_limited=scope)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again later.",
                headers={
                    "Retry-After": str(decision.reset_s),
                    "RateLimit-Limit": str(decision.limit),
                    "RateLimit-Remaining": "0",
                    "RateLimit-Reset": str(decision.reset_s),
                },
            )
        return principal

    return dependency


llm_rate_limited = rate_limited("llm")
search_rate_limited = rate_limited("search")


def check_login_attempt(username: str | None, client_ip: str) -> None:
    """Counts a sign-in attempt against the account (if any) and the client
    address; raises 429 if either budget is spent. Runs before the password
    is checked, so failed and successful attempts count alike."""
    budgets = [("login_ip", client_ip)]
    if username is not None:
        budgets.insert(0, ("login_user", username))
    for scope, key in budgets:
        decision = limiter.check(scope, key)
        if not decision.allowed:
            # The key is not logged: a username field can hold a mistyped password.
            logger.warning("rate_limited", extra={"scope": scope, "limit": decision.limit})
            record(rate_limited=scope)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many sign-in attempts. Try again later.",
                headers={"Retry-After": str(decision.reset_s)},
            )
