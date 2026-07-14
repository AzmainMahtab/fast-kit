"""Ordering API dependency providers."""

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.event_bus import IEventBus
from app.modules.ordering.domain.interfaces import IJobRepository, IOrderRepository
from app.modules.ordering.infrastructure.persistence.repository import (
    SQLAlchemyJobRepository,
    SQLAlchemyOrderRepository,
)
from app.modules.ordering.use_cases.create_order import CreateOrderUseCase
from app.modules.ordering.use_cases.get_order import GetOrderUseCase
from app.modules.ordering.use_cases.list_orders import ListOrdersUseCase
from app.modules.ordering.use_cases.transition_job_status import (
    TransitionJobStatusUseCase,
)


def get_event_bus(request: Request) -> IEventBus:
    return request.app.state.event_bus


async def get_order_repo(db: AsyncSession = Depends(get_db)) -> IOrderRepository:
    return SQLAlchemyOrderRepository(db)


async def get_job_repo(db: AsyncSession = Depends(get_db)) -> IJobRepository:
    return SQLAlchemyJobRepository(db)


async def get_create_order_use_case(
    order_repo: IOrderRepository = Depends(get_order_repo),
    job_repo: IJobRepository = Depends(get_job_repo),
    event_bus: IEventBus = Depends(get_event_bus),
) -> CreateOrderUseCase:
    return CreateOrderUseCase(
        order_repo=order_repo,
        job_repo=job_repo,
        event_bus=event_bus,
    )


async def get_transition_job_status_use_case(
    job_repo: IJobRepository = Depends(get_job_repo),
    event_bus: IEventBus = Depends(get_event_bus),
) -> TransitionJobStatusUseCase:
    return TransitionJobStatusUseCase(
        job_repo=job_repo,
        event_bus=event_bus,
    )


async def get_get_order_use_case(
    order_repo: IOrderRepository = Depends(get_order_repo),
) -> GetOrderUseCase:
    return GetOrderUseCase(order_repo=order_repo)


async def get_list_orders_use_case(
    order_repo: IOrderRepository = Depends(get_order_repo),
) -> ListOrdersUseCase:
    return ListOrdersUseCase(order_repo=order_repo)
