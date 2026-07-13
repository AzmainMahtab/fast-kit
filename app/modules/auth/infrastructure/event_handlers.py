from collections.abc import Callable, Coroutine
from typing import Any

from app.core.cache import ICacheService
from app.modules.user.domain.events import UserUpdatedEvent


def create_invalidate_user_caches_handler(
    cache: ICacheService,
) -> Callable[[UserUpdatedEvent], Coroutine[Any, Any, None]]:
    """Return an event handler that deletes auth-owned cache keys on user updates.

    Decouples the user module from auth cache key naming by subscribing to
    ``UserUpdatedEvent`` instead of having user use cases delete cache keys
    directly.
    """

    async def handler(event: UserUpdatedEvent) -> None:
        await cache.delete(f"profile:{event.user_uuid}")
        await cache.delete(f"auth:credentials:{event.email}")

    return handler
