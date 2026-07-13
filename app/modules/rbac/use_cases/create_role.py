from app.modules.rbac.cqrs.command import CreateRoleCommand
from app.modules.rbac.cqrs.result import RoleActionResult
from app.modules.rbac.domain.entities import Role
from app.modules.rbac.domain.exception import RoleAlreadyExistsError
from app.modules.rbac.domain.interfaces import IRbacRepository


class CreateRoleUseCase:
    def __init__(self, rbac_repo: IRbacRepository):
        self.rbac_repo = rbac_repo

    async def execute(self, command: CreateRoleCommand) -> RoleActionResult:
        existing = await self.rbac_repo.get_role_by_name(command.name)
        if existing:
            raise RoleAlreadyExistsError(f"Role '{command.name}' already exists.")

        role = Role(name=command.name, description=command.description)
        saved = await self.rbac_repo.create_role(role)
        await self.rbac_repo.commit()
        return RoleActionResult(role=saved)
