from app.modules.rbac.cqrs.query import GetRoleByUuidQuery
from app.modules.rbac.cqrs.result import RolePermissionAssignmentsResult
from app.modules.rbac.domain.exception import RoleNotFoundError
from app.modules.rbac.domain.interfaces import IRbacRepository


class GetRolePermissionAssignmentsUseCase:
    def __init__(self, rbac_repo: IRbacRepository):
        self.rbac_repo = rbac_repo

    async def by_uuid(self, query: GetRoleByUuidQuery) -> RolePermissionAssignmentsResult:
        role = await self.rbac_repo.get_role_by_uuid(query.uuid)
        if not role or role.id is None:
            raise RoleNotFoundError(f"Role with uuid {query.uuid} not found.")
        assignments = await self.rbac_repo.get_role_permission_assignments(role.id)
        return RolePermissionAssignmentsResult(assignments=assignments)
