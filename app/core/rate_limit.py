from collections.abc import Callable
from typing import Any

from fastapi import Request

from app.core.cache import ICacheService, NullCache
from app.core.exceptions import AppException


class RateLimiter:
    """Dependency-based rate limiter using Redis (or NullCache fallback).

    Tracks request counts per client IP and endpoint. Uses an atomic
    ``INCR`` on Redis; falls back to a no-op when Redis is unavailable.

    Note: this is a simple sliding-window approximation. For strict
    atomicity across distributed instances, use a dedicated rate-limiting
    service or Lua scripts.
    """

    def __init__(self, cache: ICacheService, max_requests: int, window_seconds: int):
        self._cache = cache
        self._max = max_requests
        self._window = window_seconds

    async def check(self, key: str) -> None:
        count = await self._cache.incr(key)
        if count == 1:
            # First request — set the TTL on the counter key.
            await self._cache.set_ttl(key, count, self._window)
        if count > self._max:
            raise AppException(
                code="RATE_LIMITED", status_code=429, detail="Too many requests. Please try again later."
            )


def rate_limit(max_requests: int, window_seconds: int) -> Callable[..., Any]:
    """Factory that returns a FastAPI dependency enforcing rate limits.

    Usage::

        @router.post("/login", dependencies=[Depends(rate_limit(5, 60))])
        async def login(...):
            ...
    """

    async def _dependency(request: Request) -> None:
        # In production behind a proxy, read X-Forwarded-For instead.
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:{request.url.path}:{client_ip}"
        # We cannot inject ICacheService cleanly here without Depends,
        # so we pull it from app.state which is set in lifespan.
        # Tests that skip lifespan get a no-op NullCache fallback.
        cache: ICacheService = getattr(request.app.state, "cache_service", NullCache())
        limiter = RateLimiter(cache, max_requests, window_seconds)
        await limiter.check(key)

    return _dependency
