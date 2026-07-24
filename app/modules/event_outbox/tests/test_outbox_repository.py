"""Tests for the SQLAlchemy outbox repository."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.event_outbox.infrastructure.persistence.repository import SQLAlchemyOutboxRepository


def _sync_session() -> AsyncMock:
    """Return an AsyncMock with sync add/flush/refresh so repository calls work."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_add_outbox_stages_event() -> None:
    session = _sync_session()
    repo = SQLAlchemyOutboxRepository()

    result = await repo.add_outbox(
        session,
        event_class_path="app.modules.ordering.domain.events.OrderCreated",
        payload={"order_id": 1},
        subject="events.ordering.order_created",
    )

    assert result.event_class_path == "app.modules.ordering.domain.events.OrderCreated"
    assert result.payload == {"order_id": 1}
    assert result.subject == "events.ordering.order_created"
    session.add.assert_called_once_with(result)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_get_pending_outbox_returns_unpublished_rows() -> None:
    session = _sync_session()
    pending_row = MagicMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [pending_row]
    session.execute = AsyncMock(return_value=result_mock)

    repo = SQLAlchemyOutboxRepository()
    result = await repo.get_pending_outbox(session, limit=50)

    assert result == [pending_row]
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_outbox_published_sets_timestamp() -> None:
    session = _sync_session()
    outbox_id = uuid.uuid4()
    row = MagicMock()
    session.get = AsyncMock(return_value=row)

    repo = SQLAlchemyOutboxRepository()
    await repo.mark_outbox_published(session, outbox_id)

    assert row.published_at is not None
    session.get.assert_awaited_once()
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_outbox_published_is_noop_when_missing() -> None:
    session = _sync_session()
    session.get = AsyncMock(return_value=None)

    repo = SQLAlchemyOutboxRepository()
    await repo.mark_outbox_published(session, uuid.uuid4())

    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_increment_outbox_attempts_records_error() -> None:
    session = _sync_session()
    outbox_id = uuid.uuid4()
    row = MagicMock()
    row.attempts = 0
    session.get = AsyncMock(return_value=row)

    repo = SQLAlchemyOutboxRepository()
    await repo.increment_outbox_attempts(session, outbox_id, "connection refused")

    assert row.attempts == 1
    assert row.error_message == "connection refused"
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_event_store_creates_audit_row() -> None:
    session = _sync_session()
    repo = SQLAlchemyOutboxRepository()

    result = await repo.add_event_store(
        session,
        event_type="OrderCreated",
        event_class_path="app.modules.ordering.domain.events.OrderCreated",
        payload={"order_id": 1},
        aggregate_id="1",
        correlation_id="corr-123",
    )

    assert result.event_type == "OrderCreated"
    assert result.aggregate_id == "1"
    assert result.correlation_id == "corr-123"
    session.add.assert_called_once_with(result)


@pytest.mark.asyncio
async def test_add_dead_letter_creates_row() -> None:
    session = _sync_session()
    repo = SQLAlchemyOutboxRepository()

    result = await repo.add_dead_letter(
        session,
        event_class_path="app.modules.ordering.domain.events.OrderCreated",
        payload={"order_id": 1},
        subject="events.ordering.order_created",
        error_message="handler failed",
        attempts=3,
    )

    assert result.error_message == "handler failed"
    assert result.attempts == 3
    session.add.assert_called_once_with(result)
