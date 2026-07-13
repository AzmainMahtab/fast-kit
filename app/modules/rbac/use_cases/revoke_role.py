from app.core.cache import ICacheService
from app.modules.rbac.cqrs.command import RevokeRoleCommand
from app.modules.rbac.domain.exception import RoleNotAssignedError, RoleNotFoundError
from app.modules.rbac.domain.interfaces import IRbacRepository


class RevokeRoleUseCase:
    def __init__(self, rbac_repo: IRbacRepository, cache: ICacheService | None = None):
        self.rbac_repo = rbac_repo
        self.cache = cache

    async def execute(self, command: RevokeRoleCommand) -> None:
        role = await self.rbac_repo.get_role_by_uuid(command.role_uuid)
        if not role or role.id is None:
            raise RoleNotFoundError(f"Role with uuid {command.role_uuid} not found.")

        has_role = await self.rbac_repo.user_has_role(command.user_id, role.name)
        if not has_role:
            raise RoleNotAssignedError(f"User does not have role '{role.name}'.")

        await self.rbac_repo.remove_role_from_user(command.user_id, role.id)
        await self.rbac_repo.commit()

        if self.cache:
            await self.cache.delete(f"user_permissions:{command.user_id}")
