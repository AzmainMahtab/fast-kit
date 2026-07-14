from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.core.event_bus import InMemoryEventBus


@dataclass(frozen=True)
class SampleEvent:
    value: str


@dataclass(frozen=True)
class OtherSampleEvent:
    value: int


@pytest.mark.asyncio
async def test_publish_calls_subscribed_handler() -> None:
    bus = InMemoryEventBus()
    results: list[str] = []

    async def handler(event: SampleEvent) -> None:
        results.append(event.value)

    bus.subscribe(SampleEvent, handler)
    await bus.publish(SampleEvent("hello"))

    assert results == ["hello"]


@pytest.mark.asyncio
async def test_publish_calls_multiple_handlers() -> None:
    bus = InMemoryEventBus()
    results: list[str] = []

    async def handler_a(event: SampleEvent) -> None:
        results.append(f"a:{event.value}")

    async def handler_b(event: SampleEvent) -> None:
        results.append(f"b:{event.value}")

    bus.subscribe(SampleEvent, handler_a)
    bus.subscribe(SampleEvent, handler_b)
    await bus.publish(SampleEvent("test"))

    assert results == ["a:test", "b:test"]


@pytest.mark.asyncio
async def test_publish_no_handlers_does_not_raise() -> None:
    bus = InMemoryEventBus()
    await bus.publish(SampleEvent("no-op"))


@pytest.mark.asyncio
async def test_publish_only_correct_type() -> None:
    bus = InMemoryEventBus()
    test_results: list[str] = []

    async def handler(event: SampleEvent) -> None:
        test_results.append(event.value)

    bus.subscribe(SampleEvent, handler)
    await bus.publish(OtherSampleEvent(42))

    assert test_results == []


@pytest.mark.asyncio
async def test_handler_receives_correct_event_instance() -> None:
    bus = InMemoryEventBus()
    received: list[SampleEvent] = []

    async def handler(event: SampleEvent) -> None:
        received.append(event)

    bus.subscribe(SampleEvent, handler)
    event = SampleEvent("check")
    await bus.publish(event)

    assert received == [event]


@pytest.mark.asyncio
async def test_publish_durable_uses_normal_publish_for_in_memory_bus() -> None:
    bus = InMemoryEventBus()
    received: list[SampleEvent] = []

    async def handler(event: SampleEvent) -> None:
        received.append(event)

    bus.subscribe(SampleEvent, handler)
    session = AsyncMock()

    await bus.publish_durable(SampleEvent("durable"), session)

    assert len(received) == 1
    assert received[0].value == "durable"


@pytest.mark.asyncio
async def test_relay_pending_outbox_is_noop_for_in_memory_bus() -> None:
    bus = InMemoryEventBus()
    session = AsyncMock()

    await bus.relay_pending_outbox(session)

    session.assert_not_awaited()
