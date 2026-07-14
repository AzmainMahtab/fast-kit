"""SQLAlchemy implementation of the outbox repository."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.event_outbox.domain.interfaces import IOutboxRepository
from app.modules.event_outbox.infrastructure.persistence.models import (
    DeadLetterEventModel,
    EventOutboxModel,
    EventStoreModel,
)


class SQLAlchemyOutboxRepository(IOutboxRepository):
    """PostgreSQL-backed outbox repository."""

    async def add_outbox(
        self, session: AsyncSession, event_class_path: str, payload: dict[str, Any], subject: str
    ) -> EventOutboxModel:
        model = EventOutboxModel(
            event_class_path=event_class_path,
            payload=payload,
            subject=subject,
        )
        session.add(model)
        await session.flush()
        await session.refresh(model)
        return model

    async def get_pending_outbox(
        self, session: AsyncSession, limit: int = 100
    ) -> Sequence[EventOutboxModel]:
        result = await session.execute(
            select(EventOutboxModel)
            .where(EventOutboxModel.published_at.is_(None))
            .order_by(EventOutboxModel.created_at)
            .limit(limit)
        )
        return result.scalars().all()

    async def mark_outbox_published(self, session: AsyncSession, outbox_id: UUID) -> None:
        model = await session.get(EventOutboxModel, outbox_id)
        if model is not None:
            model.published_at = datetime.now(UTC)
            await session.flush()

    async def increment_outbox_attempts(
        self, session: AsyncSession, outbox_id: UUID, error_message: str
    ) -> None:
        model = await session.get(EventOutboxModel, outbox_id)
        if model is not None:
            model.attempts += 1
            model.error_message = error_message
            await session.flush()

    async def add_event_store(
        self,
        session: AsyncSession,
        *,
        event_type: str,
        event_class_path: str,
        payload: dict[str, Any],
        subject: str,
        aggregate_id: str | None,
        correlation_id: str | None,
    ) -> EventStoreModel:
        model = EventStoreModel(
            event_type=event_type,
            event_class_path=event_class_path,
            payload=payload,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            published_at=datetime.now(UTC),
        )
        session.add(model)
        await session.flush()
        await session.refresh(model)
        return model

    async def add_dead_letter(
        self,
        session: AsyncSession,
        *,
        event_class_path: str,
        payload: dict[str, Any],
        subject: str,
        error_message: str,
        attempts: int,
    ) -> DeadLetterEventModel:
        model = DeadLetterEventModel(
            event_class_path=event_class_path,
            payload=payload,
            subject=subject,
            error_message=error_message,
            attempts=attempts,
        )
        session.add(model)
        await session.flush()
        await session.refresh(model)
        return model
