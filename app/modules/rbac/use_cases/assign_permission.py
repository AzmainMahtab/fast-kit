from app.modules.rbac.cqrs.command import AssignPermissionToRoleCommand
from app.modules.rbac.domain.exception import PermissionNotFoundError, RoleNotFoundError
from app.modules.rbac.domain.interfaces import IRbacRepository


class AssignPermissionToRoleUseCase:
    def __init__(self, rbac_repo: IRbacRepository):
        self.rbac_repo = rbac_repo

    async def execute(self, command: AssignPermissionToRoleCommand) -> None:
        role = await self.rbac_repo.get_role_by_uuid(command.role_uuid)
        if not role:
            raise RoleNotFoundError(f"Role with uuid {command.role_uuid} not found.")

        permission = await self.rbac_repo.get_permission_by_uuid(command.permission_uuid)
        if not permission:
            raise PermissionNotFoundError(f"Permission with uuid {command.permission_uuid} not found.")

        await self.rbac_repo.assign_permission_to_role(
            role.id, permission.id, assigned_by=command.assigned_by
        )
