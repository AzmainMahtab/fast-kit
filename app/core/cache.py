import json
from abc import ABC, abstractmethod
from typing import Any, cast

from redis.asyncio import Redis

from app.core.settings import settings


class ICacheService(ABC):
    """Abstract cache interface providing async get/set/delete/exists operations.

    Implementations can back onto Redis, an in-memory store, or a no-op
    ``NullCache`` for graceful degradation.
    """

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Retrieve a value by key.

        Args:
            key: Cache key.

        Returns:
            The deserialized value, or ``None`` if the key does not exist.
        """

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Store a value with a TTL.

        Args:
            key: Cache key.
            value: Any JSON-serializable value.
            ttl: Time-to-live in seconds.
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove a key from the cache.

        Args:
            key: Cache key to delete.
        """

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check whether a key exists in the cache.

        Args:
            key: Cache key.

        Returns:
            ``True`` if the key exists, ``False`` otherwise.
        """

    @abstractmethod
    async def incr(self, key: str) -> int:
        """Atomically increment a counter key by 1.

        Returns the new counter value. If the key does not exist it is
        created with a value of 1.
        """

    @abstractmethod
    async def set_ttl(self, key: str, value: Any, ttl: int) -> None:
        """Alias for ``set``. Provided for semantic clarity.

        Args:
            key: Cache key.
            value: Any JSON-serializable value.
            ttl: Time-to-live in seconds.
        """


class RedisCache(ICacheService):
    """Production cache implementation backed by Redis.

    Serializes values as JSON and stores them with ``SETEX``.
    """

    def __init__(self, client: Redis):
        self._client = client

    async def get(self, key: str) -> Any | None:
        raw = await self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        raw = json.dumps(value, default=str)
        await self._client.setex(key, ttl, raw)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def exists(self, key: str) -> bool:
        result = await self._client.exists(key)
        return cast(bool, result > 0)

    async def incr(self, key: str) -> int:
        return cast(int, await self._client.incr(key))

    async def set_ttl(self, key: str, value: Any, ttl: int) -> None:
        await self.set(key, value, ttl)


class NullCache(ICacheService):
    """No-op cache used when Redis is unavailable.

    All operations are silently discarded so the application can degrade
    gracefully without caching.
    """

    async def get(self, key: str) -> Any | None:
        return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        pass

    async def delete(self, key: str) -> None:
        pass

    async def exists(self, key: str) -> bool:
        return False

    async def incr(self, key: str) -> int:
        return 1

    async def set_ttl(self, key: str, value: Any, ttl: int) -> None:
        pass


async def create_redis_client() -> Redis:
    """Create an async Redis client from ``settings.REDIS_URL``.

    Returns:
        A ``redis.asyncio.Redis`` instance connected to the configured URL.
    """
    return Redis.from_url(settings.REDIS_URL, decode_responses=False)
