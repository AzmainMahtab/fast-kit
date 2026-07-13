from app.modules.rbac.cqrs.command import CreatePermissionCommand
from app.modules.rbac.cqrs.result import PermissionActionResult
from app.modules.rbac.domain.entities import Permission
from app.modules.rbac.domain.exception import PermissionAlreadyExistsError
from app.modules.rbac.domain.interfaces import IRbacRepository


class CreatePermissionUseCase:
    def __init__(self, rbac_repo: IRbacRepository):
        self.rbac_repo = rbac_repo

    async def execute(self, command: CreatePermissionCommand) -> PermissionActionResult:
        existing = await self.rbac_repo.get_permission_by_name(command.name)
        if existing:
            raise PermissionAlreadyExistsError(f"Permission '{command.name}' already exists.")

        permission = Permission(
            name=command.name, description=command.description, resource=command.resource, action=command.action
        )
        saved = await self.rbac_repo.create_permission(permission)
        await self.rbac_repo.commit()
        return PermissionActionResult(permission=saved)
