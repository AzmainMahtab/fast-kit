"""Unit tests for NATS dead-letter routing.

These cover the decision logic with test doubles and always run. The real
JetStream round-trip is covered by ``test_nats_dlq_integration.py``.
"""

import base64
import dataclasses
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from nats.js.api import ConsumerConfig

from app.core.nats_bus import (
    DLQ_HEADER_DELIVERY_COUNT,
    DLQ_HEADER_ERROR,
    DLQ_HEADER_ORIGIN_SUBJECT,
    UNPARSABLE_EVENT_CLASS,
    NatsEventBus,
    _dlq_subject_for_subject,
    _num_delivered,
    _origin_subject_for_dlq_subject,
)
from app.core.settings import settings


def _make_msg(
    subject: str,
    num_delivered: int,
    data: bytes = b"{}",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    msg = MagicMock()
    msg.subject = subject
    msg.data = data
    msg.headers = headers
    msg.metadata.num_delivered = num_delivered
    msg.ack = AsyncMock()
    msg.nak = AsyncMock()
    return msg


def _make_bus() -> tuple[NatsEventBus, AsyncMock]:
    """Return a bus plus a direct handle on its stubbed JetStream context.

    Asserting through ``bus._js`` would fight its ``JetStreamContext | None`` type.
    """
    bus = NatsEventBus(outbox_repository=MagicMock())
    js = AsyncMock()
    bus._js = js
    return bus, js


class TestSubjectMapping:
    def test_dlq_subject_is_outside_the_events_subject_space(self) -> None:
        """Regression: overlapping subjects make JetStream reject the DLQ stream."""
        dlq = _dlq_subject_for_subject("events.ordering.order_created")

        assert dlq == "dlq.ordering.order_created"
        assert not dlq.startswith(f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.")

    def test_origin_subject_round_trips(self) -> None:
        origin = "events.ordering.order_created"

        assert _origin_subject_for_dlq_subject(_dlq_subject_for_subject(origin)) == origin


class TestConsumerConfig:
    def test_consumer_config_accepts_the_arguments_we_pass(self) -> None:
        """Regression: ``dead_letter`` is not a ConsumerConfig field and raised TypeError."""
        field_names = {f.name for f in dataclasses.fields(ConsumerConfig)}

        assert "dead_letter" not in field_names
        for passed in ("name", "durable_name", "max_deliver", "deliver_policy", "ack_policy"):
            assert passed in field_names


class TestDeliveryFailure:
    async def test_naks_while_attempts_remain(self) -> None:
        bus, js = _make_bus()
        msg = _make_msg("events.ordering.order_created", num_delivered=1)

        await bus._handle_delivery_failure(msg, "ValueError: boom")

        msg.nak.assert_awaited_once()
        msg.ack.assert_not_awaited()
        js.publish.assert_not_awaited()

    async def test_routes_to_dlq_when_attempts_exhausted(self) -> None:
        bus, js = _make_bus()
        msg = _make_msg(
            "events.ordering.order_created",
            num_delivered=settings.NATS_CONSUMER_MAX_DELIVER,
            data=b'{"event_class":"x","payload":{}}',
        )

        await bus._handle_delivery_failure(msg, "ValueError: boom")

        js.publish.assert_awaited_once()
        subject, payload = js.publish.await_args.args
        assert subject == "dlq.ordering.order_created"
        assert payload == msg.data

        headers = js.publish.await_args.kwargs["headers"]
        assert headers[DLQ_HEADER_ERROR] == "ValueError: boom"
        assert headers[DLQ_HEADER_ORIGIN_SUBJECT] == "events.ordering.order_created"
        assert headers[DLQ_HEADER_DELIVERY_COUNT] == str(settings.NATS_CONSUMER_MAX_DELIVER)

    async def test_acks_original_only_after_dlq_publish_succeeds(self) -> None:
        bus, _js = _make_bus()
        msg = _make_msg("events.ordering.order_created", settings.NATS_CONSUMER_MAX_DELIVER)

        await bus._handle_delivery_failure(msg, "ValueError: boom")

        msg.ack.assert_awaited_once()
        msg.nak.assert_not_awaited()

    async def test_does_not_ack_when_dlq_publish_fails(self) -> None:
        """The event must stay recoverable rather than be silently dropped."""
        bus, js = _make_bus()
        js.publish.side_effect = RuntimeError("nats down")
        msg = _make_msg("events.ordering.order_created", settings.NATS_CONSUMER_MAX_DELIVER)

        await bus._handle_delivery_failure(msg, "ValueError: boom")

        msg.ack.assert_not_awaited()
        msg.nak.assert_awaited_once()

    async def test_does_not_ack_when_not_connected(self) -> None:
        bus, _js = _make_bus()
        bus._js = None
        msg = _make_msg("events.ordering.order_created", settings.NATS_CONSUMER_MAX_DELIVER)

        await bus._handle_delivery_failure(msg, "ValueError: boom")

        msg.ack.assert_not_awaited()
        msg.nak.assert_awaited_once()

    def test_missing_metadata_is_treated_as_final_attempt(self) -> None:
        class CoreMessage:
            """A non-JetStream message: accessing ``metadata`` raises."""

            subject = "events.ordering.order_created"

            @property
            def metadata(self) -> Any:
                raise Exception("not a JetStream message")

        assert _num_delivered(CoreMessage(), 3) == 3  # type: ignore[arg-type]


class TestHandlerFailureRouting:
    async def test_handler_exception_reaches_dlq_routing(self) -> None:
        """End-to-end through _handle_message: a raising handler dead-letters."""
        from app.modules.ordering.domain.events import OrderCreated

        bus, js = _make_bus()

        async def failing_handler(_: Any) -> None:
            raise ValueError("handler exploded")

        bus.subscribe(OrderCreated, failing_handler)

        event = OrderCreated(
            order_id=1,
            order_number="ORD-001",
            user_id=42,
            job_ids=["job-1"],
        )
        from app.core.event_serializer import serialize

        msg = _make_msg(
            "events.ordering.order_created",
            num_delivered=settings.NATS_CONSUMER_MAX_DELIVER,
            data=serialize(event).to_json(),
        )

        await bus._handle_message(msg, OrderCreated)

        js.publish.assert_awaited_once()
        assert js.publish.await_args.args[0] == "dlq.ordering.order_created"
        headers = js.publish.await_args.kwargs["headers"]
        assert "handler exploded" in headers[DLQ_HEADER_ERROR]
        msg.ack.assert_awaited_once()


class TestStartConsuming:
    async def test_creates_a_consumer_for_every_registered_event_type(self) -> None:
        """Regression: the old sequential loop blocked on the first consumer forever."""
        from app.modules.ordering.domain.events import JobStatusCheckScheduled, OrderCreated

        bus, _js = _make_bus()

        async def handler(_: Any) -> None:
            return None

        bus.subscribe(OrderCreated, handler)
        bus.subscribe(JobStatusCheckScheduled, handler)

        created: list[type] = []

        async def fake_create(event_type: type) -> Any:
            created.append(event_type)
            return MagicMock()

        consumed: list[type] = []

        async def fake_loop(_sub: Any, event_type: type) -> None:
            consumed.append(event_type)

        bus._create_consumer = fake_create  # type: ignore[method-assign]
        bus._consume_loop = fake_loop  # type: ignore[method-assign,assignment]

        await bus.start_consuming()

        assert created == [OrderCreated, JobStatusCheckScheduled]
        assert consumed == [OrderCreated, JobStatusCheckScheduled]

    async def test_returns_when_no_handlers_registered(self) -> None:
        bus, _js = _make_bus()

        await bus.start_consuming()  # must not hang or raise

    async def test_raises_when_not_connected(self) -> None:
        bus = NatsEventBus(outbox_repository=MagicMock())

        with pytest.raises(RuntimeError, match="not connected"):
            await bus.start_consuming()


class TestPoisonMessages:
    """A message that cannot be deserialized must not be silently dropped."""

    async def test_invalid_json_is_dead_lettered_not_acked_away(self) -> None:
        bus, js = _make_bus()
        msg = _make_msg("events.ordering.order_created", num_delivered=1, data=b"not json")

        await bus._handle_message(msg, object)

        js.publish.assert_awaited_once()
        assert js.publish.await_args.args[0] == "dlq.ordering.order_created"
        assert js.publish.await_args.args[1] == b"not json"
        msg.ack.assert_awaited_once()

    async def test_unimportable_event_class_is_dead_lettered(self) -> None:
        bus, js = _make_bus()
        msg = _make_msg(
            "events.ordering.order_created",
            num_delivered=1,
            data=b'{"event_class":"nope.NotAThing","payload":{}}',
        )

        await bus._handle_message(msg, object)

        js.publish.assert_awaited_once()
        msg.ack.assert_awaited_once()

    async def test_poison_message_is_not_retried_first(self) -> None:
        """Deserialization is deterministic, so retrying would fail identically."""
        bus, _js = _make_bus()
        msg = _make_msg("events.ordering.order_created", num_delivered=1, data=b"not json")

        await bus._handle_message(msg, object)

        msg.nak.assert_not_awaited()

    async def test_poison_message_is_not_acked_if_dlq_publish_fails(self) -> None:
        bus, js = _make_bus()
        js.publish.side_effect = RuntimeError("nats down")
        msg = _make_msg("events.ordering.order_created", num_delivered=1, data=b"not json")

        await bus._handle_message(msg, object)

        msg.ack.assert_not_awaited()
        msg.nak.assert_awaited_once()


class TestDlqPersistenceRetry:
    """A failed dead-letter write must be retried, not discarded."""

    def _dlq_msg(self, num_delivered: int) -> MagicMock:
        return _make_msg(
            "dlq.ordering.order_created",
            num_delivered=num_delivered,
            data=b'{"event_class":"x.Y","payload":{}}',
        )

    async def test_db_failure_naks_with_backoff_while_attempts_remain(self) -> None:
        bus, _js = _make_bus()
        bus._outbox_repository.add_dead_letter = AsyncMock(side_effect=RuntimeError("db down"))  # type: ignore[method-assign,assignment]
        msg = self._dlq_msg(num_delivered=1)

        await bus._persist_dlq_message(msg)

        msg.ack.assert_not_awaited()
        msg.nak.assert_awaited_once()
        assert msg.nak.await_args.kwargs["delay"] == (
            settings.NATS_DLQ_RETRY_BASE_DELAY_SECONDS
        )

    async def test_backoff_grows_with_delivery_count(self) -> None:
        bus, _js = _make_bus()
        bus._outbox_repository.add_dead_letter = AsyncMock(side_effect=RuntimeError("db down"))  # type: ignore[method-assign,assignment]
        msg = self._dlq_msg(num_delivered=3)

        await bus._persist_dlq_message(msg)

        assert msg.nak.await_args.kwargs["delay"] == (
            settings.NATS_DLQ_RETRY_BASE_DELAY_SECONDS * 4
        )

    async def test_backoff_is_capped(self) -> None:
        bus, _js = _make_bus()
        bus._outbox_repository.add_dead_letter = AsyncMock(side_effect=RuntimeError("db down"))  # type: ignore[method-assign,assignment]
        msg = self._dlq_msg(num_delivered=1)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(settings, "NATS_DLQ_CONSUMER_MAX_DELIVER", 50)
            mp.setattr(settings, "NATS_DLQ_RETRY_MAX_DELAY_SECONDS", 7.0)
            msg.metadata.num_delivered = 20
            await bus._persist_dlq_message(msg)

        assert msg.nak.await_args.kwargs["delay"] == 7.0

    async def test_gives_up_without_delay_once_attempts_exhausted(self) -> None:
        bus, _js = _make_bus()
        bus._outbox_repository.add_dead_letter = AsyncMock(side_effect=RuntimeError("db down"))  # type: ignore[method-assign,assignment]
        msg = self._dlq_msg(num_delivered=settings.NATS_DLQ_CONSUMER_MAX_DELIVER)

        await bus._persist_dlq_message(msg)

        msg.ack.assert_not_awaited()
        msg.nak.assert_awaited_once_with()

    async def test_dlq_consumer_gets_more_than_one_attempt(self) -> None:
        """Regression: max_deliver=1 meant one DB blip discarded the dead letter."""
        assert settings.NATS_DLQ_CONSUMER_MAX_DELIVER > 1


class TestUnparsableDlqPayload:
    """An undecodable dead letter is persisted verbatim rather than dropped."""

    async def test_raw_bytes_are_persisted(self) -> None:
        bus, _js = _make_bus()
        recorded: dict[str, Any] = {}

        async def capture(_session: Any, **kwargs: Any) -> Any:
            recorded.update(kwargs)
            return MagicMock()

        bus._outbox_repository.add_dead_letter = capture  # type: ignore[method-assign,assignment]
        msg = _make_msg("dlq.ordering.order_created", num_delivered=1, data=b"\xff\xfe not json")

        await bus._persist_dlq_message(msg)

        assert recorded["event_class_path"] == UNPARSABLE_EVENT_CLASS
        assert base64.b64decode(recorded["payload"]["raw_base64"]) == b"\xff\xfe not json"
        assert recorded["subject"] == "events.ordering.order_created"
        msg.ack.assert_awaited_once()

    async def test_preview_is_human_readable(self) -> None:
        bus, _js = _make_bus()
        recorded: dict[str, Any] = {}

        async def capture(_session: Any, **kwargs: Any) -> Any:
            recorded.update(kwargs)
            return MagicMock()

        bus._outbox_repository.add_dead_letter = capture  # type: ignore[method-assign,assignment]
        msg = _make_msg("dlq.ordering.order_created", num_delivered=1, data=b"{oops")

        await bus._persist_dlq_message(msg)

        assert recorded["payload"]["raw_preview"] == "{oops"
