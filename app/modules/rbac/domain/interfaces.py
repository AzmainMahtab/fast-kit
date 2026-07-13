from abc import ABC, abstractmethod

from app.core.pagination import PaginationParams
from app.modules.rbac.domain.entities import Permission, Role, RolePermissionAssignment, UserRoleAssignment


class IRbacRepository(ABC):
    @abstractmethod
    async def commit(self) -> None:
        """Persist all pending changes to the underlying store."""
        pass

    # Permissions
    @abstractmethod
    async def create_permission(self, permission: Permission) -> Permission:
        pass

    @abstractmethod
    async def get_permission_by_name(self, name: str) -> Permission | None:
        pass

    @abstractmethod
    async def get_permission_by_uuid(self, uuid: str) -> Permission | None:
        pass

    @abstractmethod
    async def list_permissions(self, pagination: PaginationParams = PaginationParams()) -> tuple[list[Permission], int]:
        pass

    # Roles
    @abstractmethod
    async def create_role(self, role: Role) -> Role:
        pass

    @abstractmethod
    async def get_role_by_name(self, name: str) -> Role | None:
        pass

    @abstractmethod
    async def get_role_by_uuid(self, uuid: str) -> Role | None:
        pass

    @abstractmethod
    async def list_roles(self, pagination: PaginationParams = PaginationParams()) -> tuple[list[Role], int]:
        pass

    # Role <-> Permission
    @abstractmethod
    async def assign_permission_to_role(self, role_id: int, permission_id: int, assigned_by: int | None = None) -> None:
        pass

    @abstractmethod
    async def remove_permission_from_role(self, role_id: int, permission_id: int) -> None:
        pass

    @abstractmethod
    async def get_role_permissions(self, role_id: int) -> list[Permission]:
        pass

    # User <-> Role
    @abstractmethod
    async def assign_role_to_user(self, user_id: int, role_id: int, assigned_by: int | None = None) -> None:
        pass

    @abstractmethod
    async def remove_role_from_user(self, user_id: int, role_id: int) -> None:
        pass

    @abstractmethod
    async def get_user_roles(self, user_id: int) -> list[Role]:
        pass

    @abstractmethod
    async def get_user_permissions(self, user_id: int) -> list[Permission]:
        pass

    @abstractmethod
    async def user_has_permission(self, user_id: int, permission_name: str) -> bool:
        pass

    @abstractmethod
    async def user_has_role(self, user_id: int, role_name: str) -> bool:
        pass

    @abstractmethod
    async def get_user_ids_for_role(self, role_id: int) -> list[int]:
        pass

    @abstractmethod
    async def get_user_role_assignments(self, user_id: int) -> list[UserRoleAssignment]:
        pass

    @abstractmethod
    async def get_role_permission_assignments(self, role_id: int) -> list[RolePermissionAssignment]:
        pass
