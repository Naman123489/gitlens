"""Rate-limit dependencies."""

from __future__ import annotations

from fastapi import Depends, Request

from app.core.config import get_settings
from app.core.deps import CurrentUser
from app.core.ratelimit import RateLimiter
from app.services.queue import get_redis

_limiter: RateLimiter | None = None


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(get_redis())
    return _limiter


def analysis_rate_limit(user: CurrentUser) -> None:
    """Cap how many analyses one account can start per hour.

    Repository analysis clones and parses whole repositories, so it is the one
    endpoint where an unbounded caller could exhaust the workers.
    """
    settings = get_settings()
    get_limiter().enforce(
        key=f"analysis:{user.id}", limit=settings.rate_limit_analysis_per_hour,
        window_seconds=3600, what="analysis requests",
    )


def global_rate_limit(request: Request) -> None:
    settings = get_settings()
    identity = getattr(getattr(request.state, "user", None), "id", None)
    if identity is None:
        identity = request.client.host if request.client else "anonymous"
    get_limiter().enforce(
        key=f"api:{identity}", limit=settings.rate_limit_per_minute, window_seconds=60,
    )
