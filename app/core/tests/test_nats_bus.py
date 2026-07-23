"""Tests for NATS event bus helpers."""

from dataclasses import dataclass

from app.core.nats_bus import (
    _camel_to_snake,
    _dlq_subject_for_event_type,
    _durable_name,
    _module_name_for_event,
    _subject_for_event_type,
)


@dataclass
class OrderCreated:
    order_id: int


class TestNatsSubjectMapping:
    def test_module_name_for_event(self):
        assert _module_name_for_event(OrderCreated) == "test_nats_bus"

    def test_subject_for_event_type(self):
        subject = _subject_for_event_type(OrderCreated)
        assert subject == "events.test_nats_bus.order_created"

    def test_dlq_subject_for_event_type(self):
        # The DLQ subject space is disjoint from the events space: JetStream
        # refuses to create streams whose subjects overlap.
        subject = _dlq_subject_for_event_type(OrderCreated)
        assert subject == "dlq.test_nats_bus.order_created"

    def test_durable_name(self):
        assert _durable_name("events.ordering.order_created") == "events_ordering_order_created"

    def test_camel_to_snake(self):
        assert _camel_to_snake("OrderCreated") == "order_created"
        assert _camel_to_snake("HTTPResponse") == "h_t_t_p_response"
