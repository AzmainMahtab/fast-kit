from app.core.cache import ICacheService
from app.modules.rbac.cqrs.command import AssignRoleCommand
from app.modules.rbac.domain.exception import RoleAlreadyAssignedError, RoleNotFoundError
from app.modules.rbac.domain.interfaces import IRbacRepository


class AssignRoleUseCase:
    def __init__(self, rbac_repo: IRbacRepository, cache: ICacheService | None = None):
        self.rbac_repo = rbac_repo
        self.cache = cache

    async def execute(self, command: AssignRoleCommand) -> None:
        role = await self.rbac_repo.get_role_by_uuid(command.role_uuid)
        if not role or role.id is None:
            raise RoleNotFoundError(f"Role with uuid {command.role_uuid} not found.")

        already_has = await self.rbac_repo.user_has_role(command.user_id, role.name)
        if already_has:
            raise RoleAlreadyAssignedError(f"User already has role '{role.name}'.")

        await self.rbac_repo.assign_role_to_user(command.user_id, role.id, assigned_by=command.assigned_by)
        await self.rbac_repo.commit()

        if self.cache:
            await self.cache.delete(f"user_permissions:{command.user_id}")
