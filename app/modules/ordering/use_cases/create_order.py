"""Create order use case."""

from app.core.event_bus import IEventBus
from app.modules.ordering.cqrs.command import CreateOrderCommand
from app.modules.ordering.cqrs.result import OrderResult
from app.modules.ordering.domain.entities import Job, Order
from app.modules.ordering.domain.events import OrderCreated
from app.modules.ordering.domain.interfaces import IJobRepository, IOrderRepository
from app.modules.ordering.domain.state_machine import JobStateMachine


class CreateOrderUseCase:
    """Create a new order with production jobs and publish a domain event."""

    def __init__(
        self,
        order_repo: IOrderRepository,
        job_repo: IJobRepository,
        event_bus: IEventBus,
    ):
        self.order_repo = order_repo
        self.job_repo = job_repo
        self.event_bus = event_bus

    async def execute(self, command: CreateOrderCommand) -> OrderResult:
        order = Order(order_number=command.order_number, user_id=command.user_id)
        saved_order = await self.order_repo.create(order)

        saved_jobs: list[Job] = []
        for job_input in command.jobs:
            job = Job(
                order_id=saved_order.id,
                job_id=job_input["job_id"],
                job_status=JobStateMachine.PENDING,
                file_editable=True,
            )
            saved_jobs.append(await self.job_repo.create(job))

        await self.order_repo.commit()

        saved_order.jobs = saved_jobs

        await self.event_bus.publish(
            OrderCreated(
                order_id=saved_order.id,
                order_number=saved_order.order_number,
                user_id=saved_order.user_id,
                job_ids=[j.job_id for j in saved_jobs],
            )
        )

        return OrderResult(order=saved_order)
