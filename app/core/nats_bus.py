"""NATS JetStream event bus implementation."""

import json
import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

import nats
from nats.js.api import ConsumerConfig, RetentionPolicy, StorageType, StreamConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.event_bus import IEventBus, InMemoryEventBus
from app.core.event_serializer import EventSerializationError, SerializedEvent, deserialize, serialize
from app.core.settings import settings
from app.modules.event_outbox.domain.interfaces import IOutboxRepository
from app.modules.event_outbox.infrastructure.persistence.repository import SQLAlchemyOutboxRepository

logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


def _subject_for_event_type(event_type: type) -> str:
    """Map an event class to a NATS subject.

    Example: app.modules.ordering.domain.events.OrderCreated ->
             events.ordering.order_created
    """
    module_name = _module_name_for_event(event_type)
    name = event_type.__name__
    # Convert CamelCase to snake_case and drop Event suffix
    snake = _camel_to_snake(name).removesuffix("_event")
    parts = [settings.NATS_EVENTS_SUBJECT_PREFIX, module_name, snake]
    return ".".join(parts)


def _dlq_subject_for_event_type(event_type: type) -> str:
    """DLQ subject for a given event type.

    Example: events.ordering.dlq
    """
    module_name = _module_name_for_event(event_type)
    return ".".join([settings.NATS_EVENTS_SUBJECT_PREFIX, module_name, "dlq"])


def _module_name_for_event(event_type: type) -> str:
    module_parts = event_type.__module__.split(".")
    # Drop 'app.modules.' prefix and '.domain.events' suffix
    if module_parts[:2] == ["app", "modules"]:
        module_parts = module_parts[2:]
    if module_parts and module_parts[-1] == "events":
        module_parts = module_parts[:-2]  # drop 'domain.events'
    elif len(module_parts) >= 2 and module_parts[-2] == "domain":
        module_parts = module_parts[:-2]
    return module_parts[0] if module_parts else "unknown"


def _camel_to_snake(name: str) -> str:
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def _aggregate_id_from_event(event: Any) -> str | None:
    """Best-effort aggregate ID extraction from common event field names."""
    payload = getattr(event, "__dict__", {})
    for key in ("order_id", "job_id", "user_id", "aggregate_id", "id"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    return None


class NatsEventBus(IEventBus):
    """Production-grade event bus backed by NATS JetStream.

    Features:
    - Durable event streaming with JetStream
    - Pull-based work queues for background workers
    - Per-event-type subjects
    - Dead-letter stream for failed deliveries
    - Outbox pattern for atomic DB writes + event publication
    """

    def __init__(
        self,
        nats_url: str | None = None,
        outbox_repository: IOutboxRepository | None = None,
    ):
        self.nats_url = nats_url or settings.NATS_URL
        self._nc: nats.NATS | None = None
        self._js: nats.js.JetStreamContext | None = None
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)
        self._subscribers: list[nats.js.JetStreamContext.PullSubscription] = []
        self._outbox_repository = outbox_repository or SQLAlchemyOutboxRepository()

    async def connect(self) -> None:
        self._nc = await nats.connect(self.nats_url)
        self._js = self._nc.jetstream()
        await self._ensure_streams()

    async def close(self) -> None:
        for sub in self._subscribers:
            await sub.unsubscribe()
        if self._nc:
            await self._nc.close()
        self._nc = None
        self._js = None

    async def _ensure_streams(self) -> None:
        """Create the main events stream and DLQ stream if they don't exist."""
        try:
            await self._js.add_stream(
                StreamConfig(
                    name=settings.NATS_EVENTS_STREAM,
                    subjects=[f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.>"],
                    retention=RetentionPolicy.WORK_QUEUE,
                    storage=StorageType.FILE,
                )
            )
            logger.info("Created JetStream stream %s", settings.NATS_EVENTS_STREAM)
        except nats.js.errors.BadRequestError:
            logger.debug("JetStream stream %s already exists", settings.NATS_EVENTS_STREAM)

        try:
            await self._js.add_stream(
                StreamConfig(
                    name=settings.NATS_DLQ_STREAM,
                    subjects=[f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.*.dlq"],
                    retention=RetentionPolicy.LIMITS,
                    storage=StorageType.FILE,
                )
            )
            logger.info("Created JetStream DLQ stream %s", settings.NATS_DLQ_STREAM)
        except nats.js.errors.BadRequestError:
            logger.debug("JetStream DLQ stream %s already exists", settings.NATS_DLQ_STREAM)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        """Register a local handler.

        For NATS-backed handlers, use ``start_consuming`` in the worker process.
        """
        self._handlers[event_type].append(handler)

    async def publish(self, event: Any) -> None:
        """Publish an event to JetStream.

        Local in-memory subscribers are also invoked immediately so the API
        process can react synchronously when needed. Every successful NATS
        publish is also recorded in the event store for audit/replay.
        """
        await self._publish_to_nats(event)
        await self._invoke_local_handlers(event)
        await self._record_event_store(event)

    async def publish_raw(self, subject: str, payload: bytes) -> None:
        """Publish a raw payload to a NATS subject without side effects.

        This is used by operational replay endpoints to re-send stored events
        exactly as they were originally published. It does not invoke local
        handlers or write to the event store.
        """
        if not self._js:
            raise RuntimeError("NATS event bus is not connected")
        await self._js.publish(subject, payload)
        logger.debug("Replayed raw event to %s", subject)

    async def publish_durable(self, event: Any, session: AsyncSession) -> None:
        """Write the event to the outbox table as part of the caller's transaction."""
        try:
            serialized = serialize(event)
        except EventSerializationError:
            logger.exception("Failed to serialize event %s", type(event).__name__)
            return

        subject = _subject_for_event_type(type(event))
        await self._outbox_repository.add_outbox(
            session,
            event_class_path=serialized.event_class,
            payload=serialized.payload,
            subject=subject,
        )
        logger.debug("Staged %s in outbox for subject %s", type(event).__name__, subject)

    async def relay_pending_outbox(self, session: AsyncSession) -> None:
        """Publish pending outbox rows to NATS and record them in the event store."""
        if not self._js:
            logger.warning("NATS not connected; skipping outbox relay")
            return

        pending = await self._outbox_repository.get_pending_outbox(session)
        if not pending:
            return

        for row in pending:
            await self._relay_outbox_row(session, row)

    async def _relay_outbox_row(self, session: AsyncSession, row: Any) -> None:
        if not self._js:
            logger.warning("NATS not connected; outbox row %s will remain pending", row.id)
            return

        try:
            serialized = SerializedEvent(event_class=row.event_class_path, payload=row.payload)
            await self._js.publish(row.subject, serialized.to_json())
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            logger.exception("Failed to relay outbox row %s: %s", row.id, error_message)
            await self._outbox_repository.increment_outbox_attempts(
                session, row.id, error_message
            )
            return

        await self._outbox_repository.mark_outbox_published(session, row.id)

        try:
            event = deserialize(serialized)
            aggregate_id = _aggregate_id_from_event(event)
        except EventSerializationError:
            logger.exception("Failed to deserialize outbox row %s for event store", row.id)
            aggregate_id = None

        await self._outbox_repository.add_event_store(
            session,
            event_type=row.event_class_path.rsplit(".", 1)[-1],
            event_class_path=row.event_class_path,
            payload=row.payload,
            aggregate_id=aggregate_id,
            correlation_id=None,
        )
        logger.debug("Relayed outbox row %s to %s", row.id, row.subject)

    async def _publish_to_nats(self, event: Any) -> None:
        if not self._js:
            raise RuntimeError("NATS event bus is not connected")

        try:
            serialized = serialize(event)
        except EventSerializationError:
            logger.exception("Failed to serialize event %s", type(event).__name__)
            return

        subject = _subject_for_event_type(type(event))
        await self._js.publish(subject, serialized.to_json())
        logger.debug("Published %s to %s", type(event).__name__, subject)

    async def _record_event_store(self, event: Any) -> None:
        """Persist the event to the event store in a separate session.

        This is intentionally non-transactional: the event has already been
        published to NATS, so the store is an audit trail rather than a
        correctness mechanism.
        """
        try:
            serialized = serialize(event)
        except EventSerializationError:
            logger.exception("Failed to serialize event for event store %s", type(event).__name__)
            return

        try:
            event = deserialize(serialized)
        except EventSerializationError:
            logger.exception("Failed to deserialize event for event store %s", serialized.event_class)
            event = None

        aggregate_id = _aggregate_id_from_event(event) if event is not None else None

        async with AsyncSessionLocal() as session:
            try:
                await self._outbox_repository.add_event_store(
                    session,
                    event_type=serialized.event_class.rsplit(".", 1)[-1],
                    event_class_path=serialized.event_class,
                    payload=serialized.payload,
                    aggregate_id=aggregate_id,
                    correlation_id=None,
                )
                await session.commit()
            except Exception:
                logger.exception("Failed to write event store audit row")
                await session.rollback()

    async def _invoke_local_handlers(self, event: Any) -> None:
        for handler in self._handlers.get(type(event), []):
            try:
                await handler(event)
            except Exception:
                logger.exception("Error handling event %s", type(event).__name__)

    async def start_consuming(self) -> None:
        """Start pull consumers for all registered event types.

        This is intended to run inside a dedicated worker process.
        """
        if not self._js:
            raise RuntimeError("NATS event bus is not connected")

        for event_type in self._handlers:
            await self._start_consumer(event_type)

    async def _start_consumer(self, event_type: type) -> None:
        subject = _subject_for_event_type(event_type)
        durable_name = _durable_name(subject)
        dlq_subject = _dlq_subject_for_event_type(event_type)

        try:
            sub = await self._js.pull_subscribe(
                subject,
                config=ConsumerConfig(
                    name=durable_name,
                    durable_name=durable_name,
                    max_deliver=settings.NATS_CONSUMER_MAX_DELIVER,
                    deliver_policy=nats.js.api.DeliverPolicy.ALL,
                    ack_policy=nats.js.api.AckPolicy.EXPLICIT,
                    dead_letter=dlq_subject,
                ),
            )
            self._subscribers.append(sub)
            logger.info("Started NATS consumer for %s on %s", event_type.__name__, subject)
        except nats.js.errors.BadRequestError:
            logger.warning("Consumer for %s may already exist", subject)
            return

        # Run consumer loop for this subject
        while True:
            try:
                msgs = await sub.fetch(batch=10, timeout=5)
            except nats.errors.TimeoutError:
                continue

            for msg in msgs:
                await self._handle_message(msg, event_type)

    async def _handle_message(self, msg: nats.aio.msg.Msg, event_type: type) -> None:
        try:
            serialized = SerializedEvent.from_json(msg.data)
            event = deserialize(serialized)
        except (EventSerializationError, KeyError, json.JSONDecodeError) as exc:
            logger.exception("Failed to deserialize message: %s", exc)
            await msg.ack()
            return

        try:
            for handler in self._handlers.get(event_type, []):
                await handler(event)
            await msg.ack()
        except Exception:
            logger.exception("Handler failed for %s", event_type.__name__)
            # NATS will redeliver up to max_deliver, then route to DLQ if configured
            await msg.nak()

    async def start_dlq_consuming(self) -> None:
        """Start a pull consumer for the NATS DLQ stream.

        Failed messages are persisted to ``DeadLetterEventModel`` so operators
        can inspect and replay them. This is intended to run inside the worker
        process alongside ``start_consuming``.
        """
        if not self._js:
            raise RuntimeError("NATS event bus is not connected")

        dlq_subject = f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.*.dlq"
        durable_name = _durable_name(f"{settings.NATS_EVENTS_SUBJECT_PREFIX}_dlq")

        try:
            sub = await self._js.pull_subscribe(
                dlq_subject,
                config=ConsumerConfig(
                    name=durable_name,
                    durable_name=durable_name,
                    max_deliver=1,
                    deliver_policy=nats.js.api.DeliverPolicy.ALL,
                    ack_policy=nats.js.api.AckPolicy.EXPLICIT,
                ),
            )
            self._subscribers.append(sub)
            logger.info("Started NATS DLQ consumer on %s", dlq_subject)
        except nats.js.errors.BadRequestError:
            logger.warning("DLQ consumer may already exist")
            return

        while True:
            try:
                msgs = await sub.fetch(batch=10, timeout=5)
            except nats.errors.TimeoutError:
                continue

            for msg in msgs:
                await self._persist_dlq_message(msg)

    async def _persist_dlq_message(self, msg: nats.aio.msg.Msg) -> None:
        """Persist a NATS DLQ message to the dead-letter table."""
        try:
            serialized = SerializedEvent.from_json(msg.data)
        except (EventSerializationError, KeyError, json.JSONDecodeError) as exc:
            logger.exception("Failed to deserialize DLQ message: %s", exc)
            await msg.ack()
            return

        try:
            event = deserialize(serialized)
            subject = _subject_for_event_type(type(event))
        except EventSerializationError:
            logger.exception("Failed to deserialize DLQ event %s", serialized.event_class)
            subject = f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.unknown"

        error_message = "Exceeded max delivery attempts"
        if msg.headers:
            error_message = msg.headers.get("Nats-Last-Error") or error_message

        async with AsyncSessionLocal() as session:
            try:
                await self._outbox_repository.add_dead_letter(
                    session,
                    event_class_path=serialized.event_class,
                    payload=serialized.payload,
                    subject=subject,
                    error_message=error_message,
                    attempts=settings.NATS_CONSUMER_MAX_DELIVER,
                )
                await session.commit()
                await msg.ack()
                logger.debug("Persisted DLQ message for %s", serialized.event_class)
            except Exception:
                logger.exception("Failed to persist DLQ message")
                await session.rollback()
                await msg.nak()


def _durable_name(subject: str) -> str:
    """Create a NATS-safe durable consumer name from a subject."""
    return subject.replace(".", "_").replace("*", "all").replace(">", "all")


async def create_event_bus() -> IEventBus:
    """Factory that returns the configured event bus."""
    if settings.NATS_ENABLED:
        bus = NatsEventBus()
        await bus.connect()
        return bus
    return InMemoryEventBus()
