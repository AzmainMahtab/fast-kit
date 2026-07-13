from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.modules.car.domain.entities import Car
from app.modules.car.domain.interfaces import ICarRepository
from app.modules.car.infrastructure.persistence.mapper import map_to_domain, map_to_persistence
from app.modules.car.infrastructure.persistence.models import CarModel


class SQLAlchemyCarRepository(ICarRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def get_by_id(self, car_id: int) -> Car | None:
        orm_car = await self.session.get(CarModel, car_id)
        return map_to_domain(orm_car) if orm_car else None

    async def get_by_uuid(self, uuid: str) -> Car | None:
        stmt = select(CarModel).where(CarModel.uuid == uuid)
        result = await self.session.execute(stmt)
        orm_car = result.scalar_one_or_none()
        return map_to_domain(orm_car) if orm_car else None

    async def create(self, car: Car) -> Car:
        orm_car = map_to_persistence(car)
        self.session.add(orm_car)
        await self.session.flush()
        await self.session.refresh(orm_car)
        return map_to_domain(orm_car)

    async def list_by_owner(
        self, owner_id: int, pagination: PaginationParams = PaginationParams()
    ) -> tuple[list[Car], int]:
        base = select(CarModel).where(CarModel.owner_id == owner_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = base.offset(pagination.offset).limit(pagination.limit)
        result = await self.session.execute(stmt)
        orm_cars = result.scalars().all()

        return [map_to_domain(c) for c in orm_cars], total

    async def list_all(self, pagination: PaginationParams = PaginationParams()) -> tuple[list[Car], int]:
        base = select(CarModel)

        count_stmt = select(func.count()).select_from(base.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = base.offset(pagination.offset).limit(pagination.limit)
        result = await self.session.execute(stmt)
        orm_cars = result.scalars().all()

        return [map_to_domain(c) for c in orm_cars], total
