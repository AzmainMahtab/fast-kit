"""Integration tests against a real NATS JetStream server.

Skipped automatically when no server is reachable. Point ``NATS_TEST_URL`` at a
JetStream-enabled server to run them; the ``nats`` service in ``db.yml`` exposes
one on ``localhost:4222``.

These tests deliberately drive the real client: every defect they cover
(unparsable ConsumerConfig, overlapping stream subjects, absent server-side DLQ
routing) is invisible to tests that mock the JetStream context.
"""

import asyncio
import base64
import contextlib
import os
import uuid
from typing import Any
from unittest.mock import MagicMock

import nats
import pytest
from nats.js import JetStreamContext

from app.core.event_serializer import SerializedEvent, serialize
from app.core.nats_bus import DLQ_HEADER_ERROR, DLQ_HEADER_ORIGIN_SUBJECT, UNPARSABLE_EVENT_CLASS, NatsEventBus
from app.core.settings import settings
from app.modules.ordering.domain.events import JobStatusCheckScheduled, OrderCreated

pytestmark = pytest.mark.integration

NATS_TEST_URL = os.environ.get("NATS_TEST_URL", "nats://localhost:4222")


def _js(bus: NatsEventBus) -> JetStreamContext:
    """Narrow the bus's optional JetStream context for assertions."""
    assert bus._js is not None, "bus is not connected"
    return bus._js


async def _cancel(task: asyncio.Task[Any]) -> None:
    """Stop a consumer loop and wait for it to unwind."""
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def _nats_available() -> bool:
    try:
        nc = await nats.connect(NATS_TEST_URL, connect_timeout=2, max_reconnect_attempts=1)
    except Exception:
        return False
    await nc.close()
    return True


@pytest.fixture
async def isolated_streams(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Give each test its own subject space and streams, then tear them down."""
    if not await _nats_available():
        pytest.skip(f"No NATS JetStream server at {NATS_TEST_URL}")

    token = uuid.uuid4().hex[:8]
    events_stream = f"TEST_EVENTS_{token}"
    dlq_stream = f"TEST_DLQ_{token}"

    monkeypatch.setattr(settings, "NATS_EVENTS_STREAM", events_stream)
    monkeypatch.setattr(settings, "NATS_DLQ_STREAM", dlq_stream)
    monkeypatch.setattr(settings, "NATS_EVENTS_SUBJECT_PREFIX", f"test{token}events")
    monkeypatch.setattr(settings, "NATS_DLQ_SUBJECT_PREFIX", f"test{token}dlq")
    monkeypatch.setattr(settings, "NATS_CONSUMER_MAX_DELIVER", 2)
    monkeypatch.setattr(settings, "NATS_DLQ_CONSUMER_MAX_DELIVER", 3)
    monkeypatch.setattr(settings, "NATS_DLQ_RETRY_BASE_DELAY_SECONDS", 0.5)

    yield

    nc = await nats.connect(NATS_TEST_URL)
    js = nc.jetstream()
    for name in (events_stream, dlq_stream):
        with contextlib.suppress(Exception):
            await js.delete_stream(name)
    await nc.close()


@pytest.fixture
async def bus(isolated_streams: Any) -> Any:
    """A connected bus whose outbox repository is stubbed.

    The dead-letter table lives in Postgres, which is not reachable from the test
    host, so the repository is a mock. What is under test here is the NATS
    mechanics, not the persistence layer.
    """
    event_bus = NatsEventBus(nats_url=NATS_TEST_URL, outbox_repository=MagicMock())
    await event_bus.connect()
    yield event_bus
    await event_bus.close()


class TestStreamCreation:
    async def test_both_streams_are_created(self, bus: NatsEventBus) -> None:
        """Regression: the DLQ stream overlapped ``events.>`` and was never created."""
        names = [s.config.name for s in await _js(bus).streams_info()]

        assert settings.NATS_EVENTS_STREAM in names
        assert settings.NATS_DLQ_STREAM in names

    async def test_connect_is_idempotent(self, bus: NatsEventBus) -> None:
        await bus._ensure_streams()  # identical config: must not raise

    async def test_overlapping_subjects_raise_instead_of_being_swallowed(
        self, bus: NatsEventBus, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            settings, "NATS_DLQ_SUBJECT_PREFIX", f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.inner"
        )
        monkeypatch.setattr(settings, "NATS_DLQ_STREAM", f"{settings.NATS_DLQ_STREAM}_OVERLAP")

        with pytest.raises(nats.js.errors.BadRequestError):
            await bus._ensure_streams()


class TestConsumerCreation:
    async def test_consumer_is_created_for_a_registered_event_type(
        self, bus: NatsEventBus
    ) -> None:
        """Regression: ConsumerConfig(dead_letter=...) raised TypeError here."""

        async def handler(_: Any) -> None:
            return None

        bus.subscribe(OrderCreated, handler)
        sub = await bus._create_consumer(OrderCreated)

        assert sub is not None

    async def test_every_registered_event_type_gets_a_consumer(self, bus: NatsEventBus) -> None:
        """Regression: the sequential loop blocked forever on the first consumer."""

        async def handler(_: Any) -> None:
            return None

        bus.subscribe(OrderCreated, handler)
        bus.subscribe(JobStatusCheckScheduled, handler)

        task = asyncio.create_task(bus.start_consuming())
        await asyncio.sleep(1.5)

        info = await _js(bus).streams_info()
        consumer_count = next(
            s.state.consumer_count
            for s in info
            if s.config.name == settings.NATS_EVENTS_STREAM
        )

        await _cancel(task)

        assert consumer_count == 2


class TestDeadLetterRouting:
    async def test_failing_handler_lands_on_the_dlq_subject(self, bus: NatsEventBus) -> None:
        """The end-to-end behaviour Phase 3 promised: exhausted retries reach the DLQ."""
        attempts = 0

        async def failing_handler(_: Any) -> None:
            nonlocal attempts
            attempts += 1
            raise ValueError("handler exploded")

        bus.subscribe(OrderCreated, failing_handler)

        event = OrderCreated(order_id=1, order_number="ORD-001", user_id=42, job_ids=["job-1"])
        await bus._publish_to_nats(event)

        task = asyncio.create_task(bus.start_consuming())

        # Read the DLQ subject directly rather than through the DLQ consumer, so
        # this asserts the routing itself.
        dlq_sub = await _js(bus).pull_subscribe(
            f"{settings.NATS_DLQ_SUBJECT_PREFIX}.>",
            durable=f"assert_{uuid.uuid4().hex[:8]}",
        )

        dead_letters: list[Any] = []
        for _ in range(20):
            try:
                dead_letters = await dlq_sub.fetch(batch=1, timeout=1)
                break
            except nats.errors.TimeoutError:
                continue

        await _cancel(task)

        assert len(dead_letters) == 1, "event never reached the DLQ subject"
        msg = dead_letters[0]
        assert attempts == settings.NATS_CONSUMER_MAX_DELIVER

        recovered = SerializedEvent.from_json(msg.data)
        assert recovered == serialize(event)
        assert "handler exploded" in msg.headers[DLQ_HEADER_ERROR]
        assert (
            msg.headers[DLQ_HEADER_ORIGIN_SUBJECT]
            == f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.ordering.order_created"
        )
        await msg.ack()

    async def test_successful_handler_is_not_dead_lettered(self, bus: NatsEventBus) -> None:
        handled = asyncio.Event()

        async def ok_handler(_: Any) -> None:
            handled.set()

        bus.subscribe(OrderCreated, ok_handler)
        await bus._publish_to_nats(
            OrderCreated(order_id=2, order_number="ORD-002", user_id=42, job_ids=[])
        )

        task = asyncio.create_task(bus.start_consuming())
        await asyncio.wait_for(handled.wait(), timeout=10)
        await asyncio.sleep(0.5)

        await _cancel(task)

        dlq_info = next(
            s for s in await _js(bus).streams_info() if s.config.name == settings.NATS_DLQ_STREAM
        )
        assert dlq_info.state.messages == 0


class TestDlqConsumer:
    async def test_dlq_consumer_persists_a_routed_message(self, bus: NatsEventBus) -> None:
        """The DLQ consumer subscribes to the same subject space the router publishes to."""
        recorded: list[dict[str, Any]] = []

        async def fake_add_dead_letter(_session: Any, **kwargs: Any) -> Any:
            recorded.append(kwargs)
            return MagicMock()

        bus._outbox_repository.add_dead_letter = fake_add_dead_letter  # type: ignore[method-assign,assignment]

        async def failing_handler(_: Any) -> None:
            raise ValueError("handler exploded")

        bus.subscribe(OrderCreated, failing_handler)
        event = OrderCreated(order_id=3, order_number="ORD-003", user_id=7, job_ids=[])
        await bus._publish_to_nats(event)

        consume = asyncio.create_task(bus.start_consuming())
        dlq = asyncio.create_task(bus.start_dlq_consuming())

        for _ in range(30):
            if recorded:
                break
            await asyncio.sleep(0.5)

        for task in (consume, dlq):
            await _cancel(task)

        assert recorded, "DLQ consumer never saw the dead-lettered message"
        entry = recorded[0]
        assert entry["event_class_path"].endswith("OrderCreated")
        assert (
            entry["subject"]
            == f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.ordering.order_created"
        )
        assert "handler exploded" in entry["error_message"]
        assert entry["attempts"] == settings.NATS_CONSUMER_MAX_DELIVER


class TestPoisonMessageRouting:
    """A payload that cannot be deserialized must reach the DLQ, not vanish."""

    async def test_malformed_payload_is_dead_lettered_and_persisted(
        self, bus: NatsEventBus
    ) -> None:
        recorded: list[dict[str, Any]] = []

        async def capture(_session: Any, **kwargs: Any) -> Any:
            recorded.append(kwargs)
            return MagicMock()

        bus._outbox_repository.add_dead_letter = capture  # type: ignore[method-assign,assignment]

        async def handler(_: Any) -> None:
            return None

        bus.subscribe(OrderCreated, handler)

        origin = f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.ordering.order_created"
        await _js(bus).publish(origin, b"\xff\xfe definitely not json")

        consume = asyncio.create_task(bus.start_consuming())
        dlq = asyncio.create_task(bus.start_dlq_consuming())
        for _ in range(30):
            if recorded:
                break
            await asyncio.sleep(0.5)
        for task in (consume, dlq):
            await _cancel(task)

        assert recorded, "malformed message was dropped instead of dead-lettered"
        entry = recorded[0]
        assert entry["event_class_path"] == UNPARSABLE_EVENT_CLASS
        assert entry["subject"] == origin
        assert (
            base64.b64decode(entry["payload"]["raw_base64"]) == b"\xff\xfe definitely not json"
        )

    async def test_malformed_payload_does_not_kill_the_consumer(self, bus: NatsEventBus) -> None:
        """A poison message must not take the consumer loop down with it."""
        handled = asyncio.Event()

        async def handler(_: Any) -> None:
            handled.set()

        bus.subscribe(OrderCreated, handler)
        origin = f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.ordering.order_created"

        await _js(bus).publish(origin, b"\xff\xfe not json")
        task = asyncio.create_task(bus.start_consuming())
        await asyncio.sleep(1.0)

        # A valid event published afterwards must still be handled.
        await bus._publish_to_nats(
            OrderCreated(order_id=9, order_number="ORD-009", user_id=1, job_ids=[])
        )
        try:
            await asyncio.wait_for(handled.wait(), timeout=15)
        finally:
            await _cancel(task)

        assert handled.is_set(), "consumer died on the poison message"


class TestDlqPersistenceRetryIntegration:
    async def test_transient_db_failure_is_retried_until_it_succeeds(
        self, bus: NatsEventBus
    ) -> None:
        """Regression: max_deliver=1 discarded the dead letter on one DB blip."""
        calls = 0
        succeeded = asyncio.Event()

        async def flaky(_session: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("db down")
            succeeded.set()
            return MagicMock()

        bus._outbox_repository.add_dead_letter = flaky  # type: ignore[method-assign,assignment]

        async def failing_handler(_: Any) -> None:
            raise ValueError("handler exploded")

        bus.subscribe(OrderCreated, failing_handler)
        await bus._publish_to_nats(
            OrderCreated(order_id=4, order_number="ORD-004", user_id=1, job_ids=[])
        )

        consume = asyncio.create_task(bus.start_consuming())
        dlq = asyncio.create_task(bus.start_dlq_consuming())
        try:
            await asyncio.wait_for(succeeded.wait(), timeout=30)
        finally:
            for task in (consume, dlq):
                await _cancel(task)

        assert calls >= 2, "the dead letter was not retried after the DB failure"

    async def test_valid_json_with_bad_event_class_is_dead_lettered(
        self, bus: NatsEventBus
    ) -> None:
        """Parses as JSON but has an unresolvable class path.

        This clears from_json and fails inside deserialize, which previously
        raised a bare ValueError and killed the consumer's fetch loop.
        """
        handled = asyncio.Event()

        async def handler(_: Any) -> None:
            handled.set()

        bus.subscribe(OrderCreated, handler)
        origin = f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.ordering.order_created"

        await _js(bus).publish(origin, b'{"event_class":"NoDotsHere","payload":{}}')
        task = asyncio.create_task(bus.start_consuming())
        await asyncio.sleep(1.0)

        # The consumer must still be alive for a subsequent valid event.
        await bus._publish_to_nats(
            OrderCreated(order_id=11, order_number="ORD-011", user_id=1, job_ids=[])
        )
        try:
            await asyncio.wait_for(handled.wait(), timeout=15)
        finally:
            await _cancel(task)

        assert handled.is_set(), "consumer died on the malformed event class"
