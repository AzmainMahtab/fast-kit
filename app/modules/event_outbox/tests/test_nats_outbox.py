"""Tests for NATS event bus outbox functionality."""

import json
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.nats_bus import NatsEventBus


@dataclass(frozen=True)
class OrderCreated:
    order_id: int
    order_number: str


@pytest.fixture
def mock_outbox_repository():
    return AsyncMock()


@pytest.fixture
def mock_js():
    return AsyncMock()


@pytest.fixture
def event_bus(mock_outbox_repository, mock_js):
    bus = NatsEventBus(nats_url="nats://test", outbox_repository=mock_outbox_repository)
    bus._js = mock_js
    return bus


@pytest.mark.asyncio
async def test_publish_durable_stages_event_in_outbox(event_bus, mock_outbox_repository) -> None:
    session = AsyncMock()
    event = OrderCreated(order_id=1, order_number="ORD-001")

    await event_bus.publish_durable(event, session)

    call = mock_outbox_repository.add_outbox.await_args
    assert call.args[0] is session
    assert call.kwargs["event_class_path"].endswith("test_nats_outbox.OrderCreated")
    assert call.kwargs["payload"] == {"order_id": 1, "order_number": "ORD-001"}
    assert call.kwargs["subject"] == "events.event_outbox.order_created"


@pytest.mark.asyncio
async def test_publish_durable_logs_and_returns_on_serialization_error(
    event_bus, mock_outbox_repository
) -> None:
    session = AsyncMock()
    not_an_event = {"not": "a dataclass"}

    await event_bus.publish_durable(not_an_event, session)

    mock_outbox_repository.add_outbox.assert_not_awaited()


@pytest.mark.asyncio
async def test_relay_pending_outbox_publishes_and_records_event_store(
    event_bus, mock_outbox_repository, mock_js
) -> None:
    session = AsyncMock()
    outbox_id = uuid.uuid4()
    pending_row = MagicMock()
    pending_row.id = outbox_id
    pending_row.event_class_path = "app.modules.ordering.domain.events.OrderCreated"
    pending_row.payload = {"order_id": 1}
    pending_row.subject = "events.ordering.order_created"
    mock_outbox_repository.get_pending_outbox.return_value = [pending_row]

    await event_bus.relay_pending_outbox(session)

    mock_js.publish.assert_awaited_once_with(
        "events.ordering.order_created",
        json.dumps(
            {
                "event_class": "app.modules.ordering.domain.events.OrderCreated",
                "payload": {"order_id": 1},
            }
        ).encode("utf-8"),
    )
    mock_outbox_repository.mark_outbox_published.assert_awaited_once_with(session, outbox_id)
    mock_outbox_repository.add_event_store.assert_awaited_once_with(
        session,
        event_type="OrderCreated",
        event_class_path="app.modules.ordering.domain.events.OrderCreated",
        payload={"order_id": 1},
        subject="events.ordering.order_created",
        aggregate_id=None,
        correlation_id=None,
    )


@pytest.mark.asyncio
async def test_relay_pending_outbox_increments_attempts_on_publish_failure(
    event_bus, mock_outbox_repository, mock_js
) -> None:
    session = AsyncMock()
    outbox_id = uuid.uuid4()
    pending_row = MagicMock()
    pending_row.id = outbox_id
    pending_row.event_class_path = "app.modules.ordering.domain.events.OrderCreated"
    pending_row.payload = {"order_id": 1}
    pending_row.subject = "events.ordering.order_created"
    mock_outbox_repository.get_pending_outbox.return_value = [pending_row]
    mock_js.publish.side_effect = ConnectionError("nats down")

    await event_bus.relay_pending_outbox(session)

    mock_outbox_repository.mark_outbox_published.assert_not_awaited()
    mock_outbox_repository.increment_outbox_attempts.assert_awaited_once_with(
        session, outbox_id, "ConnectionError: nats down"
    )


@pytest.mark.asyncio
async def test_relay_pending_outbox_is_noop_when_not_connected(
    event_bus, mock_outbox_repository
) -> None:
    session = AsyncMock()
    event_bus._js = None

    await event_bus.relay_pending_outbox(session)

    mock_outbox_repository.get_pending_outbox.assert_not_awaited()
