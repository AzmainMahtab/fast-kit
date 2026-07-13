from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.interfaces import IUserRepository
from app.modules.user.domain.value_objects import Email
from app.modules.user.infrastructure.persistence.mapper import map_to_domain, map_to_persistence
from app.modules.user.infrastructure.persistence.models import UserModel


class SQLAlchemyUserRepository(IUserRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def get_by_email(self, email: Email) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email.value)
        result = await self.session.execute(stmt)
        orm_user = result.scalar_one_or_none()
        return map_to_domain(orm_user) if orm_user else None

    async def get_by_id(self, user_id: int) -> User | None:
        orm_user = await self.session.get(UserModel, user_id)
        return map_to_domain(orm_user) if orm_user else None

    async def get_by_uuid(self, uuid: str) -> User | None:
        stmt = select(UserModel).where(UserModel.uuid == uuid)
        result = await self.session.execute(stmt)
        orm_user = result.scalar_one_or_none()
        return map_to_domain(orm_user) if orm_user else None

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(UserModel).where(UserModel.username == username)
        result = await self.session.execute(stmt)
        orm_user = result.scalar_one_or_none()
        return map_to_domain(orm_user) if orm_user else None

    async def create(self, user: User) -> User:
        orm_user = map_to_persistence(user)
        self.session.add(orm_user)
        await self.session.flush()
        await self.session.refresh(orm_user)
        return map_to_domain(orm_user)

    async def update(self, user: User) -> User:
        orm_user = map_to_persistence(user)
        merged_orm = await self.session.merge(orm_user)
        await self.session.flush()
        await self.session.refresh(merged_orm)
        return map_to_domain(merged_orm)

    async def delete(self, uuid: str) -> None:
        stmt = sa_delete(UserModel).where(UserModel.uuid == uuid)
        await self.session.execute(stmt)

    async def list_all(
        self,
        status: UserStatus | None = None,
        include_deleted: bool = False,
        pagination: PaginationParams = PaginationParams(),
    ) -> tuple[list[User], int]:
        base = select(UserModel)

        if not include_deleted:
            base = base.where(UserModel.deleted_at.is_(None))

        if status:
            base = base.where(UserModel.status == status.value)

        count_stmt = select(func.count()).select_from(base.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = base.offset(pagination.offset).limit(pagination.limit)
        result = await self.session.execute(stmt)
        orm_users = result.scalars().all()

        return [map_to_domain(u) for u in orm_users], total
