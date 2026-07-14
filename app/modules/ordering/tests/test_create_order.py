import pytest

from app.modules.ordering.cqrs.command import CreateOrderCommand
from app.modules.ordering.domain.events import OrderCreated
from app.modules.ordering.domain.state_machine import JobStateMachine
from app.modules.ordering.use_cases.create_order import CreateOrderUseCase


@pytest.mark.asyncio
async def test_create_order_publishes_event(order_repo, job_repo, event_bus):
    use_case = CreateOrderUseCase(
        order_repo=order_repo,
        job_repo=job_repo,
        event_bus=event_bus,
    )

    received = []

    async def handler(event):
        received.append(event)

    event_bus.subscribe(OrderCreated, handler)

    result = await use_case.execute(
        CreateOrderCommand(
            user_id=1,
            order_number="ORD-001",
            jobs=[{"job_id": "JOB-001"}, {"job_id": "JOB-002"}],
        )
    )

    assert result.order.order_number == "ORD-001"
    assert result.order.user_id == 1
    assert len(result.order.jobs) == 2
    assert result.order.jobs[0].job_status == JobStateMachine.PENDING
    assert len(received) == 1
    assert received[0].order_number == "ORD-001"
