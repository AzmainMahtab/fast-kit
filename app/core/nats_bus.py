"""NATS JetStream event bus implementation."""

import json
import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

import nats
from nats.js.api import ConsumerConfig, RetentionPolicy, StorageType, StreamConfig

from app.core.event_bus import IEventBus
from app.core.event_serializer import EventSerializationError, SerializedEvent, deserialize, serialize
from app.core.settings import settings

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


class NatsEventBus(IEventBus):
    """Production-grade event bus backed by NATS JetStream.

    Features:
    - Durable event streaming with JetStream
    - Pull-based work queues for background workers
    - Per-event-type subjects
    - Dead-letter stream for failed deliveries
    """

    def __init__(self, nats_url: str | None = None):
        self.nats_url = nats_url or settings.NATS_URL
        self._nc: nats.NATS | None = None
        self._js: nats.js.JetStreamContext | None = None
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)
        self._subscribers: list[nats.js.JetStreamContext.PullSubscription] = []

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
        process can react synchronously when needed.
        """
        await self._publish_to_nats(event)
        await self._invoke_local_handlers(event)

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
