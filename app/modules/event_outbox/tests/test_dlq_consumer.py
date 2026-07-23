"""Tests for the NATS DLQ consumer."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.event_serializer import SerializedEvent
from app.core.nats_bus import NatsEventBus


@dataclass(frozen=True)
class OrderCreated:
    order_id: int
    order_number: str


EVENT_CLASS_PATH = f"{__name__}.OrderCreated"


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
async def test_persist_dlq_message_creates_dead_letter(event_bus, mock_outbox_repository) -> None:
    serialized = SerializedEvent(
        event_class=EVENT_CLASS_PATH,
        payload={"order_id": 1, "order_number": "ORD-001"},
    )
    msg = MagicMock()
    msg.data = serialized.to_json()
    msg.headers = None
    msg.ack = AsyncMock()
    msg.nak = AsyncMock()

    await event_bus._persist_dlq_message(msg)

    call = mock_outbox_repository.add_dead_letter.await_args
    assert call.kwargs["event_class_path"] == EVENT_CLASS_PATH
    assert call.kwargs["payload"] == {"order_id": 1, "order_number": "ORD-001"}
    assert call.kwargs["subject"] == "events.event_outbox.order_created"
    assert call.kwargs["attempts"] == 3
    msg.ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_dlq_message_uses_last_error_header(event_bus, mock_outbox_repository) -> None:
    serialized = SerializedEvent(
        event_class=EVENT_CLASS_PATH,
        payload={"order_id": 1, "order_number": "ORD-001"},
    )
    msg = MagicMock()
    msg.data = serialized.to_json()
    msg.headers = {"Nats-Last-Error": "timeout"}
    msg.ack = AsyncMock()
    msg.nak = AsyncMock()

    await event_bus._persist_dlq_message(msg)

    call = mock_outbox_repository.add_dead_letter.await_args
    assert call.kwargs["error_message"] == "timeout"


@pytest.mark.asyncio
async def test_persist_dlq_message_naks_on_db_error(event_bus, mock_outbox_repository) -> None:
    mock_outbox_repository.add_dead_letter.side_effect = RuntimeError("db down")
    serialized = SerializedEvent(
        event_class=EVENT_CLASS_PATH,
        payload={"order_id": 1, "order_number": "ORD-001"},
    )
    msg = MagicMock()
    msg.data = serialized.to_json()
    msg.headers = None
    msg.ack = AsyncMock()
    msg.nak = AsyncMock()

    await event_bus._persist_dlq_message(msg)

    msg.nak.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_dlq_message_acks_invalid_json(event_bus, mock_outbox_repository) -> None:
    msg = MagicMock()
    msg.data = b"not json"
    msg.headers = None
    msg.ack = AsyncMock()
    msg.nak = AsyncMock()

    await event_bus._persist_dlq_message(msg)

    mock_outbox_repository.add_dead_letter.assert_not_awaited()
    msg.ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_dlq_message_falls_back_to_unknown_subject(event_bus, mock_outbox_repository) -> None:
    serialized = SerializedEvent(
        event_class="app.modules.event_outbox.tests.test_dlq_consumer.NonExistent",
        payload={"order_id": 1},
    )
    msg = MagicMock()
    msg.data = serialized.to_json()
    msg.headers = None
    msg.ack = AsyncMock()
    msg.nak = AsyncMock()

    await event_bus._persist_dlq_message(msg)

    call = mock_outbox_repository.add_dead_letter.await_args
    assert call.kwargs["subject"] == "events.unknown"
