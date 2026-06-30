from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import PaginationParams
from app.modules.rbac.domain.entities import Permission, Role
from app.modules.rbac.domain.interfaces import IRbacRepository
from app.modules.rbac.infrastructure.persistence.mapper import map_permission_to_domain, map_role_to_domain
from app.modules.rbac.infrastructure.persistence.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserRoleModel,
)


class SQLAlchemyRbacRepository(IRbacRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    # Permissions

    async def create_permission(self, permission: Permission) -> Permission:
        orm = PermissionModel(
            name=permission.name,
            description=permission.description,
            resource=permission.resource,
            action=permission.action,
        )
        self.session.add(orm)
        await self.session.flush()
        await self.session.refresh(orm)
        return map_permission_to_domain(orm)

    async def get_permission_by_name(self, name: str) -> Permission | None:
        stmt = select(PermissionModel).where(PermissionModel.name == name)
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        return map_permission_to_domain(orm) if orm else None

    async def get_permission_by_uuid(self, uuid: str) -> Permission | None:
        stmt = select(PermissionModel).where(PermissionModel.uuid == uuid)
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        return map_permission_to_domain(orm) if orm else None

    async def list_permissions(
        self,
        pagination: PaginationParams = PaginationParams(),
    ) -> tuple[list[Permission], int]:
        base = select(PermissionModel)
        count_stmt = select(func.count()).select_from(base.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = base.offset(pagination.offset).limit(pagination.limit)
        result = await self.session.execute(stmt)
        orms = result.scalars().all()
        return [map_permission_to_domain(o) for o in orms], total

    # Roles

    async def create_role(self, role: Role) -> Role:
        orm = RoleModel(name=role.name, description=role.description)
        self.session.add(orm)
        await self.session.flush()
        await self.session.refresh(orm)
        return map_role_to_domain(orm, include_permissions=False)

    async def get_role_by_name(self, name: str) -> Role | None:
        stmt = select(RoleModel).where(RoleModel.name == name)
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        return map_role_to_domain(orm) if orm else None

    async def get_role_by_uuid(self, uuid: str) -> Role | None:
        stmt = select(RoleModel).where(RoleModel.uuid == uuid).options(selectinload(RoleModel.permissions))
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        return map_role_to_domain(orm) if orm else None

    async def list_roles(
        self,
        pagination: PaginationParams = PaginationParams(),
    ) -> tuple[list[Role], int]:
        base = select(RoleModel).options(selectinload(RoleModel.permissions))
        count_stmt = select(func.count()).select_from(base.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = base.offset(pagination.offset).limit(pagination.limit)
        result = await self.session.execute(stmt)
        orms = result.scalars().all()
        return [map_role_to_domain(o) for o in orms], total

    # Role <-> Permission

    async def assign_permission_to_role(
        self, role_id: int, permission_id: int, assigned_by: int | None = None
    ) -> None:
        existing = await self.session.get(RolePermissionModel, (role_id, permission_id))
        if existing:
            return  # Already assigned
        self.session.add(
            RolePermissionModel(
                role_id=role_id,
                permission_id=permission_id,
                assigned_by=assigned_by,
            )
        )

    async def remove_permission_from_role(self, role_id: int, permission_id: int) -> None:
        rp = await self.session.get(RolePermissionModel, (role_id, permission_id))
        if rp:
            await self.session.delete(rp)

    async def get_role_permissions(self, role_id: int) -> list[Permission]:
        stmt = (
            select(PermissionModel)
            .join(RolePermissionModel, PermissionModel.id == RolePermissionModel.permission_id)
            .where(RolePermissionModel.role_id == role_id)
        )
        result = await self.session.execute(stmt)
        orms = result.scalars().all()
        return [map_permission_to_domain(o) for o in orms]

    # User <-> Role

    async def assign_role_to_user(
        self, user_id: int, role_id: int, assigned_by: int | None = None
    ) -> None:
        existing = await self.session.get(UserRoleModel, (user_id, role_id))
        if existing:
            return  # Already assigned
        self.session.add(
            UserRoleModel(
                user_id=user_id,
                role_id=role_id,
                assigned_by=assigned_by,
            )
        )

    async def remove_role_from_user(self, user_id: int, role_id: int) -> None:
        ur = await self.session.get(UserRoleModel, (user_id, role_id))
        if ur:
            await self.session.delete(ur)

    async def get_user_roles(self, user_id: int) -> list[Role]:
        stmt = (
            select(RoleModel)
            .join(UserRoleModel, RoleModel.id == UserRoleModel.role_id)
            .where(UserRoleModel.user_id == user_id)
            .options(selectinload(RoleModel.permissions))
        )
        result = await self.session.execute(stmt)
        orms = result.scalars().all()
        return [map_role_to_domain(o) for o in orms]

    async def get_user_permissions(self, user_id: int) -> list[Permission]:
        stmt = (
            select(PermissionModel)
            .distinct()
            .join(RolePermissionModel, PermissionModel.id == RolePermissionModel.permission_id)
            .join(UserRoleModel, RolePermissionModel.role_id == UserRoleModel.role_id)
            .where(UserRoleModel.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        orms = result.scalars().all()
        return [map_permission_to_domain(o) for o in orms]

    async def user_has_permission(self, user_id: int, permission_name: str) -> bool:
        stmt = (
            select(func.count())
            .select_from(PermissionModel)
            .join(RolePermissionModel, PermissionModel.id == RolePermissionModel.permission_id)
            .join(UserRoleModel, RolePermissionModel.role_id == UserRoleModel.role_id)
            .where(UserRoleModel.user_id == user_id, PermissionModel.name == permission_name)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def user_has_role(self, user_id: int, role_name: str) -> bool:
        stmt = (
            select(func.count())
            .select_from(RoleModel)
            .join(UserRoleModel, RoleModel.id == UserRoleModel.role_id)
            .where(UserRoleModel.user_id == user_id, RoleModel.name == role_name)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0
