"""Rate limiting.

A fixed-window counter backed by Redis when available, falling back to an
in-process window so the limiter still works in single-node development. The
fallback is explicitly *not* a distributed limiter and says so in its ``backend``
attribute, which the admin health endpoint reports.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.core.errors import RateLimitError


@dataclass(frozen=True, slots=True)
class LimitDecision:
    allowed: bool
    remaining: int
    reset_in: int
    limit: int


class RateLimiter:
    def __init__(self, redis_client: object | None = None) -> None:
        self._redis = redis_client
        self.backend = "redis" if redis_client else "in-process"
        self._local: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> LimitDecision:
        if limit <= 0:
            return LimitDecision(True, 0, window_seconds, limit)
        if self._redis is not None:
            return self._check_redis(key, limit, window_seconds)
        return self._check_local(key, limit, window_seconds)

    def enforce(self, key: str, limit: int, window_seconds: int, what: str = "requests") -> LimitDecision:
        decision = self.check(key, limit, window_seconds)
        if not decision.allowed:
            raise RateLimitError(
                f"Too many {what}. The limit is {limit} per {window_seconds} seconds; "
                f"try again in {decision.reset_in} seconds.",
                {"limit": limit, "window_seconds": window_seconds, "retry_after": decision.reset_in},
            )
        return decision

    def _check_redis(self, key: str, limit: int, window_seconds: int) -> LimitDecision:
        window = int(time.time() // window_seconds)
        redis_key = f"ratelimit:{key}:{window}"
        try:
            pipe = self._redis.pipeline()  # type: ignore[union-attr]
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds)
            count = int(pipe.execute()[0])
        except Exception:  # pragma: no cover - redis outage
            self.backend = "in-process (redis unavailable)"
            return self._check_local(key, limit, window_seconds)
        reset_in = window_seconds - int(time.time() % window_seconds)
        return LimitDecision(count <= limit, max(0, limit - count), reset_in, limit)

    def _check_local(self, key: str, limit: int, window_seconds: int) -> LimitDecision:
        now = time.time()
        with self._lock:
            count, window_start = self._local.get(key, (0, now))
            if now - window_start >= window_seconds:
                count, window_start = 0, now
            count += 1
            self._local[key] = (count, window_start)
            if len(self._local) > 50_000:  # crude bound on memory
                cutoff = now - window_seconds
                self._local = {k: v for k, v in self._local.items() if v[1] > cutoff}
        reset_in = max(0, int(window_seconds - (now - window_start)))
        return LimitDecision(count <= limit, max(0, limit - count), reset_in, limit)
