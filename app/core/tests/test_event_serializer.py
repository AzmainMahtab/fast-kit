"""Tests for event serialization."""

from dataclasses import dataclass

import pytest

from app.core.event_serializer import (
    EventSerializationError,
    SerializedEvent,
    deserialize,
    serialize,
)


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
