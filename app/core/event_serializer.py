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
    def from_json(cls, data: bytes) -> "SerializedEvent":
        try:
            decoded = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise EventSerializationError("Invalid JSON payload") from exc

        return cls(
            event_class=decoded["event_class"],
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
    """Deserialize a serialized event back to an instance."""
    module_name, class_name = serialized.event_class.rsplit(".", 1)
    try:
        module = __import__(module_name, fromlist=[class_name])
    except ImportError as exc:
        raise EventSerializationError(
            f"Cannot import module {module_name}"
        ) from exc

    try:
        event_cls = getattr(module, class_name)
    except AttributeError as exc:
        raise EventSerializationError(
            f"Class {serialized.event_class} not found"
        ) from exc

    try:
        return event_cls(**serialized.payload)
    except TypeError as exc:
        raise EventSerializationError(
            f"Cannot instantiate {serialized.event_class} with {serialized.payload}"
        ) from exc


def _json_default(obj: Any) -> Any:
    """Fallback JSON encoder for non-standard types."""
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
