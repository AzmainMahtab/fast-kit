"""Tests for event serialization."""

from dataclasses import dataclass

import pytest

from app.core.event_serializer import EventSerializationError, SerializedEvent, deserialize, serialize


@dataclass(frozen=True)
class DummyEvent:
    id: int
    name: str


def test_roundtrip_serialization():
    event = DummyEvent(id=1, name="test")
    serialized = serialize(event)

    assert serialized.event_class.endswith("test_event_serializer.DummyEvent")
    assert serialized.payload == {"id": 1, "name": "test"}

    restored = deserialize(serialized)
    assert restored == event


def test_serialize_non_dataclass_raises():
    with pytest.raises(EventSerializationError):
        serialize("not an event")


def test_deserialize_missing_class_raises():
    serialized = SerializedEvent(
        event_class="nonexistent.module.Event",
        payload={},
    )
    with pytest.raises(EventSerializationError):
        deserialize(serialized)


def test_serialized_event_to_json():
    event = DummyEvent(id=1, name="test")
    serialized = serialize(event)
    data = serialized.to_json()
    assert b"event_class" in data
    assert b"payload" in data

    restored = SerializedEvent.from_json(data)
    assert restored.event_class == serialized.event_class
    assert restored.payload == serialized.payload


class TestMalformedWirePayloads:
    """Every malformed input must raise EventSerializationError.

    These payloads arrive over NATS, so an uncaught exception here propagates out
    of the consumer's fetch loop and stops all event processing. Callers catch
    EventSerializationError to dead-letter the offending message instead.
    """

    @pytest.mark.parametrize(
        ("label", "raw"),
        [
            ("non-utf8 bytes", b"\xff\xfe"),
            ("not json", b"not json"),
            ("json array", b"[1,2]"),
            ("json string", b'"just a string"'),
            ("missing event_class", b"{}"),
            ("event_class with no dot", b'{"event_class":"Foo","payload":{}}'),
            ("event_class not a string", b'{"event_class":123,"payload":{}}'),
            ("event_class null", b'{"event_class":null,"payload":{}}'),
            ("event_class empty", b'{"event_class":"","payload":{}}'),
            ("trailing dot", b'{"event_class":"mod.","payload":{}}'),
            ("leading dot", b'{"event_class":".Cls","payload":{}}'),
            ("payload not a mapping", b'{"event_class":"a.B","payload":[1,2]}'),
            ("payload null", b'{"event_class":"a.B","payload":null}'),
            ("unimportable module", b'{"event_class":"nope.NotAThing","payload":{}}'),
        ],
    )
    def test_malformed_payload_raises_event_serialization_error(
        self, label: str, raw: bytes
    ) -> None:
        with pytest.raises(EventSerializationError):
            deserialize(SerializedEvent.from_json(raw))

    def test_signature_mismatch_raises_event_serialization_error(self) -> None:
        from app.modules.ordering.domain.events import OrderCreated

        raw = (
            b'{"event_class":"app.modules.ordering.domain.events.OrderCreated",'
            b'"payload":{"bogus":1}}'
        )
        with pytest.raises(EventSerializationError):
            deserialize(SerializedEvent.from_json(raw))

        assert OrderCreated is not None  # the class itself is importable

    def test_validation_error_in_post_init_is_wrapped(self) -> None:
        """A domain event that rejects its own payload must not escape as ValueError."""
        raw = (
            b'{"event_class":"app.core.tests.test_event_serializer.PickyEvent",'
            b'"payload":{"value":-1}}'
        )
        with pytest.raises(EventSerializationError):
            deserialize(SerializedEvent.from_json(raw))


@dataclass(frozen=True)
class PickyEvent:
    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("value must be non-negative")
