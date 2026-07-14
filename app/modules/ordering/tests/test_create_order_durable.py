"""Tests for durable (outbox-aware) order creation."""

from unittest.mock import AsyncMock

import pytest

from app.modules.ordering.cqrs.command import CreateOrderCommand
from app.modules.ordering.domain.events import OrderCreated
from app.modules.ordering.use_cases.create_order import CreateOrderUseCase


@pytest.mark.asyncio
async def test_create_order_with_session_stages_event_durably(order_repo, job_repo) -> None:
    """When a session is passed, the event is staged in the outbox, not published directly."""
    event_bus = AsyncMock()
    session = AsyncMock()
    order_repo.commit = AsyncMock()
    use_case = CreateOrderUseCase(
        order_repo=order_repo,
        job_repo=job_repo,
        event_bus=event_bus,
        session=session,
    )

    result = await use_case.execute(
        CreateOrderCommand(
            user_id=1,
            order_number="ORD-DURABLE",
            jobs=[{"job_id": "JOB-001"}],
        )
    )

    assert result.order.order_number == "ORD-DURABLE"
    event_bus.publish_durable.assert_awaited_once()
    event_bus.publish.assert_not_awaited()
    order_repo.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_order_without_session_publishes_directly(order_repo, job_repo) -> None:
    """Legacy path: without a session the event is published directly."""
    event_bus = AsyncMock()
    order_repo.commit = AsyncMock()
    use_case = CreateOrderUseCase(
        order_repo=order_repo,
        job_repo=job_repo,
        event_bus=event_bus,
    )

    await use_case.execute(
        CreateOrderCommand(
            user_id=1,
            order_number="ORD-LEGACY",
            jobs=[{"job_id": "JOB-001"}],
        )
    )

    event_bus.publish.assert_awaited_once()
    event_bus.publish_durable.assert_not_awaited()
    order_repo.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_order_durable_event_payload(order_repo, job_repo) -> None:
    """The staged event contains the correct domain payload."""
    event_bus = AsyncMock()
    session = AsyncMock()
    order_repo.commit = AsyncMock()
    use_case = CreateOrderUseCase(
        order_repo=order_repo,
        job_repo=job_repo,
        event_bus=event_bus,
        session=session,
    )

    await use_case.execute(
        CreateOrderCommand(
            user_id=42,
            order_number="ORD-PAYLOAD",
            jobs=[{"job_id": "JOB-A"}, {"job_id": "JOB-B"}],
        )
    )

    event = event_bus.publish_durable.await_args.args[0]
    assert isinstance(event, OrderCreated)
    assert event.order_number == "ORD-PAYLOAD"
    assert event.user_id == 42
    assert event.job_ids == ["JOB-A", "JOB-B"]
    assert event_bus.publish_durable.await_args.args[1] is session
