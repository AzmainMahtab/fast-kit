"""Ordering SQLAlchemy repositories."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.modules.ordering.domain.entities import Job, Order
from app.modules.ordering.domain.interfaces import IJobRepository, IOrderRepository
from app.modules.ordering.infrastructure.persistence.mapper import (
    map_job_to_domain,
    map_job_to_model,
    map_order_to_domain,
    map_order_to_model,
)
from app.modules.ordering.infrastructure.persistence.models import JobModel, OrderModel


class SQLAlchemyOrderRepository(IOrderRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def get_by_id(self, order_id: int) -> Order | None:
        result = await self.session.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        )
        model = result.scalar_one_or_none()
        return map_order_to_domain(model) if model else None

    async def list_all(
        self, pagination: PaginationParams = PaginationParams()
    ) -> tuple[list[Order], int]:
        base = select(OrderModel)
        count_stmt = select(func.count()).select_from(base.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = base.offset(pagination.offset).limit(pagination.limit)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [map_order_to_domain(m) for m in models], total

    async def create(self, order: Order) -> Order:
        model = map_order_to_model(order)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return map_order_to_domain(model)


class SQLAlchemyJobRepository(IJobRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def get_by_id(self, job_id: int) -> Job | None:
        model = await self.session.get(JobModel, job_id)
        return map_job_to_domain(model) if model else None

    async def create(self, job: Job) -> Job:
        model = map_job_to_model(job)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return map_job_to_domain(model)

    async def update(self, job: Job) -> Job:
        model = await self.session.get(JobModel, job.id)
        if model is None:
            return job
        map_job_to_model(job, existing=model)
        await self.session.flush()
        await self.session.refresh(model)
        return map_job_to_domain(model)
