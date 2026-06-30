from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.modules.owner.domain.entities import Owner
from app.modules.owner.domain.interfaces import IOwnerRepository
from app.modules.owner.infrastructure.persistence.mapper import map_to_domain, map_to_persistence
from app.modules.owner.infrastructure.persistence.models import OwnerModel


class SQLAlchemyOwnerRepository(IOwnerRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, owner_id: int) -> Owner | None:
        orm_owner = await self.session.get(OwnerModel, owner_id)
        return map_to_domain(orm_owner) if orm_owner else None

    async def get_by_uuid(self, uuid: str) -> Owner | None:
        stmt = select(OwnerModel).where(OwnerModel.uuid == uuid)
        result = await self.session.execute(stmt)
        orm_owner = result.scalar_one_or_none()
        return map_to_domain(orm_owner) if orm_owner else None

    async def get_by_user_id(self, user_id: int) -> Owner | None:
        stmt = select(OwnerModel).where(OwnerModel.user_id == user_id)
        result = await self.session.execute(stmt)
        orm_owner = result.scalar_one_or_none()
        return map_to_domain(orm_owner) if orm_owner else None

    async def create(self, owner: Owner) -> Owner:
        orm_owner = map_to_persistence(owner)
        self.session.add(orm_owner)
        await self.session.flush()
        await self.session.refresh(orm_owner)
        return map_to_domain(orm_owner)

    async def list_all(
        self,
        pagination: PaginationParams = PaginationParams(),
    ) -> tuple[list[Owner], int]:
        base = select(OwnerModel)

        count_stmt = select(func.count()).select_from(base.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = base.offset(pagination.offset).limit(pagination.limit)
        result = await self.session.execute(stmt)
        orm_owners = result.scalars().all()

        return [map_to_domain(o) for o in orm_owners], total
