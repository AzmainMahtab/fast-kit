"""Outbox repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.event_outbox.infrastructure.persistence.models import (
    DeadLetterEventModel,
    EventOutboxModel,
    EventStoreModel,
)


class IOutboxRepository(ABC):
    """Persistence contract for the event outbox, event store, and dead letter."""

    @abstractmethod
    async def add_outbox(
        self, session: AsyncSession, event_class_path: str, payload: dict[str, Any], subject: str
    ) -> EventOutboxModel: ...

    @abstractmethod
    async def get_pending_outbox(
        self, session: AsyncSession, limit: int = 100
    ) -> Sequence[EventOutboxModel]: ...

    @abstractmethod
    async def mark_outbox_published(
        self, session: AsyncSession, outbox_id: UUID
    ) -> None: ...

    @abstractmethod
    async def increment_outbox_attempts(
        self, session: AsyncSession, outbox_id: UUID, error_message: str
    ) -> None: ...

    @abstractmethod
    async def add_event_store(
        self,
        session: AsyncSession,
        *,
        event_type: str,
        event_class_path: str,
        payload: dict[str, Any],
        aggregate_id: str | None,
        correlation_id: str | None,
    ) -> EventStoreModel: ...

    @abstractmethod
    async def add_dead_letter(
        self,
        session: AsyncSession,
        *,
        event_class_path: str,
        payload: dict[str, Any],
        subject: str,
        error_message: str,
        attempts: int,
    ) -> DeadLetterEventModel: ...

    @abstractmethod
    async def list_event_store(
        self,
        session: AsyncSession,
        *,
        event_type: str | None = None,
        aggregate_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[EventStoreModel]: ...

    @abstractmethod
    async def get_event_store(self, session: AsyncSession, event_id: UUID) -> EventStoreModel | None: ...

    @abstractmethod
    async def list_dead_letter(
        self,
        session: AsyncSession,
        *,
        resolved: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[DeadLetterEventModel]: ...

    @abstractmethod
    async def get_dead_letter(
        self, session: AsyncSession, dead_letter_id: UUID
    ) -> DeadLetterEventModel | None: ...

    @abstractmethod
    async def mark_dead_letter_resolved(
        self, session: AsyncSession, dead_letter_id: UUID
    ) -> DeadLetterEventModel | None: ...
