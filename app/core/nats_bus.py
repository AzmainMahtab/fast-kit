"""NATS JetStream event bus implementation."""

import asyncio
import base64
import json
import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

import nats
from nats.aio.msg import Msg
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

# JetStream API error codes we must distinguish rather than swallow.
# 10058: stream name already in use with a *different* configuration.
# 10065: the requested subjects overlap with an existing stream.
# An add_stream call with an identical configuration succeeds, so any
# BadRequestError from _ensure_stream signals real config drift.
JS_ERR_STREAM_NAME_IN_USE = 10058
JS_ERR_SUBJECT_OVERLAP = 10065

# Headers attached to a message when it is routed to the dead-letter subject.
DLQ_HEADER_ERROR = "Nats-Last-Error"
DLQ_HEADER_ORIGIN_SUBJECT = "X-Origin-Subject"
DLQ_HEADER_DELIVERY_COUNT = "X-Delivery-Count"

# Recorded as the event class when a dead-lettered payload cannot be decoded,
# so the row is still queryable and obviously distinct from a real event.
UNPARSABLE_EVENT_CLASS = "<unparsable>"


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

    Example: events.ordering.order_created -> dlq.ordering.order_created
    """
    return _dlq_subject_for_subject(_subject_for_event_type(event_type))


def _dlq_subject_for_subject(subject: str) -> str:
    """Map an origin subject onto the DLQ subject space.

    The DLQ prefix is deliberately disjoint from the events prefix: JetStream
    refuses to create two streams whose subjects overlap (err_code 10065), so
    ``dlq.>`` cannot live underneath ``events.>``.
    """
    suffix = subject.removeprefix(f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.")
    return f"{settings.NATS_DLQ_SUBJECT_PREFIX}.{suffix}"


def _origin_subject_for_dlq_subject(dlq_subject: str) -> str:
    """Inverse of :func:`_dlq_subject_for_subject`, used to replay a dead letter."""
    suffix = dlq_subject.removeprefix(f"{settings.NATS_DLQ_SUBJECT_PREFIX}.")
    return f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.{suffix}"


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
        await self._ensure_stream(
            StreamConfig(
                name=settings.NATS_EVENTS_STREAM,
                subjects=[f"{settings.NATS_EVENTS_SUBJECT_PREFIX}.>"],
                retention=RetentionPolicy.WORK_QUEUE,
                storage=StorageType.FILE,
            )
        )
        await self._ensure_stream(
            StreamConfig(
                name=settings.NATS_DLQ_STREAM,
                subjects=[f"{settings.NATS_DLQ_SUBJECT_PREFIX}.>"],
                retention=RetentionPolicy.LIMITS,
                storage=StorageType.FILE,
            )
        )

    async def _ensure_stream(self, config: StreamConfig) -> None:
        """Create a stream, treating an identical existing stream as success.

        JetStream's ``add_stream`` is idempotent when the supplied configuration
        matches the existing stream, so a ``BadRequestError`` here always means
        the deployed stream genuinely disagrees with this code. Swallowing it
        (the previous behaviour) silently left the DLQ stream uncreated.
        """
        if not self._js:
            raise RuntimeError("NATS event bus is not connected")

        try:
            await self._js.add_stream(config)
        except nats.js.errors.BadRequestError as exc:
            if exc.err_code == JS_ERR_SUBJECT_OVERLAP:
                logger.error(
                    "JetStream stream %s claims subjects %s which overlap an existing "
                    "stream; refusing to start. Check NATS_EVENTS_SUBJECT_PREFIX and "
                    "NATS_DLQ_SUBJECT_PREFIX are disjoint.",
                    config.name,
                    config.subjects,
                )
            elif exc.err_code == JS_ERR_STREAM_NAME_IN_USE:
                logger.error(
                    "JetStream stream %s already exists with a different configuration; "
                    "refusing to start. Update or delete the stream to match %s.",
                    config.name,
                    config.subjects,
                )
            raise
        logger.info("Ensured JetStream stream %s with subjects %s", config.name, config.subjects)

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

        subscriptions: list[tuple[Any, type]] = []
        for event_type in list(self._handlers):
            sub = await self._create_consumer(event_type)
            if sub is not None:
                subscriptions.append((sub, event_type))

        if not subscriptions:
            logger.warning("No NATS consumers were started; no handlers are registered")
            return

        # Each consumer runs its own fetch loop. Awaiting them sequentially would
        # block on the first loop forever and leave every other event type without
        # a consumer.
        await asyncio.gather(
            *(self._consume_loop(sub, event_type) for sub, event_type in subscriptions)
        )

    async def _create_consumer(self, event_type: type) -> Any:
        """Create the durable pull consumer for one event type.

        Returns the subscription, or ``None`` if it could not be created.
        """
        if not self._js:
            raise RuntimeError("NATS event bus is not connected")

        subject = _subject_for_event_type(event_type)
        durable_name = _durable_name(subject)

        try:
            # ``durable`` must be passed positionally to pull_subscribe rather than
            # only inside ConsumerConfig: the client derives the API subject from
            # config.name, and when durable is omitted it overwrites that name with
            # a random NUID while leaving durable_name set, which the server
            # rejects (err_code 10017). Passing durable also makes re-subscription
            # idempotent across worker restarts.
            sub = await self._js.pull_subscribe(
                subject,
                durable=durable_name,
                config=ConsumerConfig(
                    max_deliver=settings.NATS_CONSUMER_MAX_DELIVER,
                    deliver_policy=nats.js.api.DeliverPolicy.ALL,
                    ack_policy=nats.js.api.AckPolicy.EXPLICIT,
                ),
            )
        except nats.js.errors.BadRequestError:
            logger.exception("Could not create NATS consumer %s for %s", durable_name, subject)
            return None

        self._subscribers.append(sub)
        logger.info("Started NATS consumer for %s on %s", event_type.__name__, subject)
        return sub

    async def _consume_loop(self, sub: Any, event_type: type) -> None:
        while True:
            try:
                msgs = await sub.fetch(batch=10, timeout=5)
            except nats.errors.TimeoutError:
                continue

            for msg in msgs:
                await self._handle_message(msg, event_type)

    async def _handle_message(self, msg: Msg, event_type: type) -> None:
        try:
            serialized = SerializedEvent.from_json(msg.data)
            event = deserialize(serialized)
        except (EventSerializationError, KeyError, json.JSONDecodeError) as exc:
            logger.exception("Failed to deserialize message on %s", msg.subject)
            await self._route_poison_message(msg, f"{type(exc).__name__}: {exc}")
            return

        try:
            for handler in self._handlers.get(event_type, []):
                await handler(event)
            await msg.ack()
        except Exception as exc:
            logger.exception("Handler failed for %s", event_type.__name__)
            await self._handle_delivery_failure(msg, f"{type(exc).__name__}: {exc}")

    async def _handle_delivery_failure(self, msg: Msg, error_message: str) -> None:
        """Nak for another attempt, or route to the DLQ once attempts are exhausted.

        JetStream has no server-side dead-letter routing: once ``max_deliver`` is
        reached it simply stops redelivering. Under WORK_QUEUE retention an
        unacked message would then sit in the stream forever, invisible. So the
        application must publish it to the DLQ subject itself and ack the original.
        """
        delivered = _num_delivered(msg, settings.NATS_CONSUMER_MAX_DELIVER)
        if delivered < settings.NATS_CONSUMER_MAX_DELIVER:
            await msg.nak()
            logger.warning(
                "Delivery %s/%s failed for %s; will retry",
                delivered,
                settings.NATS_CONSUMER_MAX_DELIVER,
                msg.subject,
            )
            return

        await self._dead_letter(msg, error_message, delivered)

    async def _route_poison_message(self, msg: Msg, error_message: str) -> None:
        """Dead-letter a message that cannot be deserialized.

        Deserialization is deterministic, so redelivery would fail identically.
        The message goes straight to the DLQ rather than burning retry attempts
        -- and, critically, rather than being acked and dropped.
        """
        await self._dead_letter(msg, error_message, _num_delivered(msg, 1))

    async def _dead_letter(self, msg: Msg, error_message: str, attempts: int) -> None:
        """Publish a copy to the DLQ subject, then ack the original."""
        if not self._js:
            logger.error("NATS not connected; cannot route %s to DLQ", msg.subject)
            await msg.nak()
            return

        dlq_subject = _dlq_subject_for_subject(msg.subject)
        try:
            await self._js.publish(
                dlq_subject,
                msg.data,
                headers={
                    DLQ_HEADER_ERROR: error_message,
                    DLQ_HEADER_ORIGIN_SUBJECT: msg.subject,
                    DLQ_HEADER_DELIVERY_COUNT: str(attempts),
                },
            )
        except Exception:
            # Leave the message unacked so it can be recovered rather than lost.
            logger.exception("Failed to route %s to DLQ subject %s", msg.subject, dlq_subject)
            await msg.nak()
            return

        # Ack only after the DLQ copy is durable, so WORK_QUEUE retention can
        # release the original without dropping the event.
        await msg.ack()
        logger.error(
            "Routed %s to DLQ %s after %s attempts: %s",
            msg.subject,
            dlq_subject,
            attempts,
            error_message,
        )

    async def start_dlq_consuming(self) -> None:
        """Start a pull consumer for the NATS DLQ stream.

        Failed messages are persisted to ``DeadLetterEventModel`` so operators
        can inspect and replay them. This is intended to run inside the worker
        process alongside ``start_consuming``.
        """
        if not self._js:
            raise RuntimeError("NATS event bus is not connected")

        dlq_subject = f"{settings.NATS_DLQ_SUBJECT_PREFIX}.>"
        durable_name = _durable_name(f"{settings.NATS_DLQ_SUBJECT_PREFIX}_consumer")

        try:
            sub = await self._js.pull_subscribe(
                dlq_subject,
                durable=durable_name,
                config=ConsumerConfig(
                    # Must exceed 1: persisting a dead letter hits PostgreSQL, and
                    # a single attempt means a transient DB outage discards it.
                    max_deliver=settings.NATS_DLQ_CONSUMER_MAX_DELIVER,
                    deliver_policy=nats.js.api.DeliverPolicy.ALL,
                    ack_policy=nats.js.api.AckPolicy.EXPLICIT,
                ),
            )
            self._subscribers.append(sub)
            logger.info("Started NATS DLQ consumer on %s", dlq_subject)
        except nats.js.errors.BadRequestError:
            logger.exception("Could not create NATS DLQ consumer %s", durable_name)
            return

        while True:
            try:
                msgs = await sub.fetch(batch=10, timeout=5)
            except nats.errors.TimeoutError:
                continue

            for msg in msgs:
                await self._persist_dlq_message(msg)

    async def _persist_dlq_message(self, msg: Msg) -> None:
        """Persist a NATS DLQ message to the dead-letter table."""
        try:
            serialized = SerializedEvent.from_json(msg.data)
            event_class_path = serialized.event_class
            payload = serialized.payload
        except (EventSerializationError, KeyError, json.JSONDecodeError):
            # The bytes are undecodable, but discarding them would lose the only
            # copy of the event. Persist them verbatim so an operator can inspect
            # and re-drive the message by hand.
            logger.exception("Unparsable DLQ payload on %s; persisting raw bytes", msg.subject)
            event_class_path = UNPARSABLE_EVENT_CLASS
            payload = {
                "raw_base64": base64.b64encode(msg.data).decode("ascii"),
                "raw_preview": msg.data[:512].decode("utf-8", errors="replace"),
            }

        # Prefer the origin subject recorded at dead-letter time; it is exact and
        # does not require the event class to still be importable. Fall back to
        # mapping the DLQ subject back onto the events subject space.
        headers = msg.headers or {}
        subject = headers.get(DLQ_HEADER_ORIGIN_SUBJECT) or _origin_subject_for_dlq_subject(
            msg.subject
        )
        error_message = headers.get(DLQ_HEADER_ERROR) or "Exceeded max delivery attempts"
        try:
            attempts = int(headers.get(DLQ_HEADER_DELIVERY_COUNT, ""))
        except ValueError:
            attempts = settings.NATS_CONSUMER_MAX_DELIVER

        async with AsyncSessionLocal() as session:
            try:
                await self._outbox_repository.add_dead_letter(
                    session,
                    event_class_path=event_class_path,
                    payload=payload,
                    subject=subject,
                    error_message=error_message,
                    attempts=attempts,
                )
                await session.commit()
            except Exception:
                logger.exception("Failed to persist DLQ message from %s", msg.subject)
                await session.rollback()
                await self._retry_or_abandon_dlq_message(msg)
                return

        await msg.ack()
        logger.debug("Persisted DLQ message for %s", event_class_path)

    async def _retry_or_abandon_dlq_message(self, msg: Msg) -> None:
        """Back off and retry a failed dead-letter write, or give up loudly.

        The write target is PostgreSQL, so failures are usually transient. Naking
        with an increasing delay avoids hammering a database that is already down.
        """
        delivered = _num_delivered(msg, settings.NATS_DLQ_CONSUMER_MAX_DELIVER)
        if delivered < settings.NATS_DLQ_CONSUMER_MAX_DELIVER:
            delay = min(
                settings.NATS_DLQ_RETRY_BASE_DELAY_SECONDS * (2 ** (delivered - 1)),
                settings.NATS_DLQ_RETRY_MAX_DELAY_SECONDS,
            )
            await msg.nak(delay=delay)
            logger.warning(
                "DLQ persist attempt %s/%s failed for %s; retrying in %ss",
                delivered,
                settings.NATS_DLQ_CONSUMER_MAX_DELIVER,
                msg.subject,
                delay,
            )
            return

        # No further redelivery is possible. The message is not lost: the DLQ
        # stream uses LIMITS retention, so it survives for manual recovery until
        # the retention window expires.
        await msg.nak()
        logger.critical(
            "Gave up persisting dead letter from %s after %s attempts. The message "
            "remains in the %s stream for manual recovery; investigate the database.",
            msg.subject,
            delivered,
            settings.NATS_DLQ_STREAM,
        )


def _num_delivered(msg: Msg, fallback: int) -> int:
    """Delivery attempt number for a JetStream message.

    Falls back to ``fallback`` when metadata is unavailable (e.g. a core NATS
    message), so an undiagnosable failure is dead-lettered rather than looping.
    The caller supplies the limit that applies to its own consumer.
    """
    try:
        return int(msg.metadata.num_delivered or 0)
    except Exception:
        logger.warning("No JetStream metadata on %s; treating as final attempt", msg.subject)
        return fallback


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
