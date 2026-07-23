"""In-memory test double for the outbox repository."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.modules.event_outbox.domain.interfaces import IOutboxRepository
from app.modules.event_outbox.infrastructure.persistence.models import (
    DeadLetterEventModel,
    EventOutboxModel,
    EventStoreModel,
)


class InMemoryOutboxRepository(IOutboxRepository):
    """Non-persistent outbox repository for unit tests."""

    def __init__(self) -> None:
        self._outbox: dict[uuid.UUID, EventOutboxModel] = {}
        self._event_store: dict[uuid.UUID, EventStoreModel] = {}
        self._dead_letter: dict[uuid.UUID, DeadLetterEventModel] = {}
        self._next_outbox_id = 1
        self._next_event_store_id = 1
        self._next_dead_letter_id = 1

    async def add_outbox(
        self, session: Any, event_class_path: str, payload: dict[str, Any], subject: str
    ) -> EventOutboxModel:
        model = EventOutboxModel(
            id=uuid.uuid4(),
            event_class_path=event_class_path,
            payload=payload,
            subject=subject,
        )
        self._outbox[model.id] = model
        return model

    async def get_pending_outbox(self, session: Any, limit: int = 100) -> Sequence[EventOutboxModel]:
        rows = [r for r in self._outbox.values() if r.published_at is None]
        return rows[:limit]

    async def mark_outbox_published(self, session: Any, outbox_id: uuid.UUID) -> None:
        model = self._outbox.get(outbox_id)
        if model is not None:
            model.published_at = datetime.now(UTC)

    async def increment_outbox_attempts(
        self, session: Any, outbox_id: uuid.UUID, error_message: str
    ) -> None:
        model = self._outbox.get(outbox_id)
        if model is not None:
            model.attempts += 1
            model.error_message = error_message

    async def add_event_store(
        self,
        session: Any,
        *,
        event_type: str,
        event_class_path: str,
        payload: dict[str, Any],
        aggregate_id: str | None,
        correlation_id: str | None,
    ) -> EventStoreModel:
        model = EventStoreModel(
            id=uuid.uuid4(),
            event_type=event_type,
            event_class_path=event_class_path,
            payload=payload,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            published_at=datetime.now(UTC),
        )
        self._event_store[model.id] = model
        return model

    async def add_dead_letter(
        self,
        session: Any,
        *,
        event_class_path: str,
        payload: dict[str, Any],
        subject: str,
        error_message: str,
        attempts: int,
    ) -> DeadLetterEventModel:
        model = DeadLetterEventModel(
            id=uuid.uuid4(),
            event_class_path=event_class_path,
            payload=payload,
            subject=subject,
            error_message=error_message,
            attempts=attempts,
            created_at=datetime.now(UTC),
        )
        self._dead_letter[model.id] = model
        return model

    async def list_event_store(
        self,
        session: Any,
        *,
        event_type: str | None = None,
        aggregate_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[EventStoreModel]:
        rows = list(self._event_store.values())
        rows.sort(key=lambda r: r.published_at, reverse=True)
        if event_type:
            rows = [r for r in rows if r.event_type == event_type]
        if aggregate_id:
            rows = [r for r in rows if r.aggregate_id == aggregate_id]
        return rows[offset : offset + limit]

    async def get_event_store(self, session: Any, event_id: uuid.UUID) -> EventStoreModel | None:
        return self._event_store.get(event_id)

    async def list_dead_letter(
        self,
        session: Any,
        *,
        resolved: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[DeadLetterEventModel]:
        rows = list(self._dead_letter.values())
        if resolved is True:
            rows = [r for r in rows if r.resolved_at is not None]
        elif resolved is False:
            rows = [r for r in rows if r.resolved_at is None]
        return rows[offset : offset + limit]

    async def get_dead_letter(
        self, session: Any, dead_letter_id: uuid.UUID
    ) -> DeadLetterEventModel | None:
        return self._dead_letter.get(dead_letter_id)

    async def mark_dead_letter_resolved(
        self, session: Any, dead_letter_id: uuid.UUID
    ) -> DeadLetterEventModel | None:
        model = self._dead_letter.get(dead_letter_id)
        if model is None:
            return None
        model.resolved_at = datetime.now(UTC)
        return model
