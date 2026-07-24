"""Serialize and deserialize domain events for transport.

Events are encoded as JSON with two top-level keys:
- ``event_class``: dotted path to the event class
- ``payload``: dataclass fields as a dict

This lets NATS JetStream or Celery reconstruct the exact event subclass
on the consumer side without the publisher and consumer sharing imports.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any


class EventSerializationError(Exception):
    """Raised when an event cannot be serialized or deserialized."""


@dataclass(frozen=True)
class SerializedEvent:
    event_class: str
    payload: dict[str, Any]

    def to_json(self) -> bytes:
        return json.dumps(
            {"event_class": self.event_class, "payload": self.payload},
            default=_json_default,
        ).encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes) -> SerializedEvent:
        """Decode a transport payload.

        Every malformed input raises ``EventSerializationError``. Callers consume
        bytes off the wire, where arbitrary junk is possible; letting
        ``UnicodeDecodeError`` or ``TypeError`` escape would kill the consumer
        loop rather than dead-letter the message.
        """
        try:
            decoded = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EventSerializationError("Invalid JSON payload") from exc

        if not isinstance(decoded, dict):
            raise EventSerializationError(
                f"Expected a JSON object, got {type(decoded).__name__}"
            )

        try:
            event_class = decoded["event_class"]
        except KeyError as exc:
            raise EventSerializationError("Payload is missing 'event_class'") from exc

        return cls(
            event_class=event_class,
            payload=decoded.get("payload", {}),
        )


def serialize(event: Any) -> SerializedEvent:
    """Serialize a dataclass event instance."""
    if not hasattr(event, "__dataclass_fields__"):
        raise EventSerializationError(f"Event {event!r} is not a dataclass")

    cls = event.__class__
    return SerializedEvent(
        event_class=f"{cls.__module__}.{cls.__qualname__}",
        payload=asdict(event),
    )


def deserialize(serialized: SerializedEvent) -> Any:
    """Deserialize a serialized event back to an instance.

    Like :meth:`SerializedEvent.from_json`, every failure surfaces as
    ``EventSerializationError``. The input originates on the wire, so
    ``event_class`` may be absent, the wrong type, or unresolvable; letting a
    raw ``ValueError``/``AttributeError`` escape would kill the consumer loop
    instead of dead-lettering the one message responsible.
    """
    event_class = serialized.event_class
    if not isinstance(event_class, str) or "." not in event_class:
        raise EventSerializationError(f"Malformed event class path: {event_class!r}")

    module_name, class_name = event_class.rsplit(".", 1)
    if not module_name or not class_name:
        raise EventSerializationError(f"Malformed event class path: {event_class!r}")

    try:
        module = __import__(module_name, fromlist=[class_name])
    except Exception as exc:
        # Importing runs module-level code, which can fail in any number of ways.
        raise EventSerializationError(f"Cannot import module {module_name}") from exc

    try:
        event_cls = getattr(module, class_name)
    except AttributeError as exc:
        raise EventSerializationError(f"Class {event_class} not found") from exc

    if not isinstance(serialized.payload, dict):
        raise EventSerializationError(
            f"Payload for {event_class} is not a JSON object: {serialized.payload!r}"
        )

    try:
        return event_cls(**serialized.payload)
    except Exception as exc:
        # Covers a signature mismatch as well as validation raised in __post_init__.
        raise EventSerializationError(
            f"Cannot instantiate {event_class} with {serialized.payload}"
        ) from exc


def _json_default(obj: Any) -> Any:
    """Fallback JSON encoder for non-standard types."""
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
