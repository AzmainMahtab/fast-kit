from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class IEventBus(ABC):
    @abstractmethod
    async def publish(self, event: Any) -> None: ...

    @abstractmethod
    def subscribe(self, event_type: type, handler: EventHandler) -> None: ...

    @abstractmethod
    async def publish_durable(self, event: Any, session: AsyncSession) -> None:
        """Write the event to the outbox table within the caller's DB transaction.

        The event is relayed to NATS after the transaction commits via
        ``relay_pending_outbox``.
        """

    @abstractmethod
    async def relay_pending_outbox(self, session: AsyncSession) -> None:
        """Publish all pending outbox rows to NATS and record them in the event store."""


class InMemoryEventBus(IEventBus):
    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Any) -> None:
        for handler in self._handlers[type(event)]:
            await handler(event)

    async def publish_durable(self, event: Any, session: AsyncSession) -> None:
        """In-memory bus is not transactional; behave like a normal publish."""
        await self.publish(event)

    async def relay_pending_outbox(self, session: AsyncSession) -> None:
        """No-op for the in-memory bus."""
