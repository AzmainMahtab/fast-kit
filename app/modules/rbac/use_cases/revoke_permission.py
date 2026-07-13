from app.core.cache import ICacheService
from app.modules.rbac.cqrs.command import RevokePermissionFromRoleCommand
from app.modules.rbac.domain.exception import PermissionNotAssignedError, PermissionNotFoundError, RoleNotFoundError
from app.modules.rbac.domain.interfaces import IRbacRepository


class RevokePermissionFromRoleUseCase:
    def __init__(self, rbac_repo: IRbacRepository, cache: ICacheService | None = None):
        self.rbac_repo = rbac_repo
        self.cache = cache

    async def execute(self, command: RevokePermissionFromRoleCommand) -> None:
        role = await self.rbac_repo.get_role_by_uuid(command.role_uuid)
        if not role or role.id is None:
            raise RoleNotFoundError(f"Role with uuid {command.role_uuid} not found.")

        permission = await self.rbac_repo.get_permission_by_uuid(command.permission_uuid)
        if not permission or permission.id is None:
            raise PermissionNotFoundError(f"Permission with uuid {command.permission_uuid} not found.")

        role_perms = await self.rbac_repo.get_role_permissions(role.id)
        assigned = any(p.id == permission.id for p in role_perms)
        if not assigned:
            raise PermissionNotAssignedError(f"Permission '{permission.name}' is not assigned to role '{role.name}'.")

        await self.rbac_repo.remove_permission_from_role(role.id, permission.id)
        await self.rbac_repo.commit()

        if self.cache:
            user_ids = await self.rbac_repo.get_user_ids_for_role(role.id)
            for uid in user_ids:
                await self.cache.delete(f"user_permissions:{uid}")
