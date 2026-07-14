"""Event outbox, event store, dead-letter, and idempotency SQLAlchemy models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BaseModelMixin


class EventOutboxModel(BaseModelMixin, Base):
    """Pending events waiting to be published to NATS.

    Written in the same database transaction as the business write,
    then relayed to NATS after the transaction commits.
    """

    __tablename__ = "event_outbox"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_class_path: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_event_outbox_published_at_created_at", "published_at", "created_at"),
    )


class EventStoreModel(BaseModelMixin, Base):
    """Immutable audit log of every event published to NATS."""

    __tablename__ = "event_store"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_class_path: Mapped[str] = mapped_column(String(255), nullable=False)
    aggregate_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class DeadLetterEventModel(BaseModelMixin, Base):
    """Events that failed delivery after max retries, persisted for inspection."""

    __tablename__ = "dead_letter_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_class_path: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProcessedEventModel(Base):
    """Idempotency guard for event handlers.

    Tracks which events have already been handled so replays and redeliveries
    do not duplicate side effects.
    """

    __tablename__ = "processed_events"

    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
