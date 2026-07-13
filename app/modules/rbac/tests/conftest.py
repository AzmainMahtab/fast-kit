from datetime import UTC, datetime
from typing import Any

import pytest
import uuid_utils

from app.core.pagination import PaginationParams
from app.modules.rbac.domain.entities import Permission, Role, RolePermissionAssignment, UserRoleAssignment
from app.modules.rbac.domain.interfaces import IRbacRepository


class InMemoryRbacRepository(IRbacRepository):
    def __init__(self) -> None:
        self._permissions: dict[int, Permission] = {}
        self._roles: dict[int, Role] = {}
        self._role_permissions: dict[int, set[int]] = {}
        self._user_roles: dict[int, set[int]] = {}
        self._role_permission_meta: dict[tuple[int, int], dict[str, Any]] = {}
        self._user_role_meta: dict[tuple[int, int], dict[str, Any]] = {}
        self._next_perm_id = 1
        self._next_role_id = 1

    async def commit(self) -> None:
        """No-op for the in-memory test double."""
        return

    # Permissions

    async def create_permission(self, permission: Permission) -> Permission:
        permission.id = self._next_perm_id
        self._next_perm_id += 1
        permission.uuid = str(uuid_utils.uuid7())
        self._permissions[permission.id] = permission
        return permission

    async def get_permission_by_name(self, name: str) -> Permission | None:
        for p in self._permissions.values():
            if p.name == name:
                return p
        return None

    async def get_permission_by_uuid(self, uuid: str) -> Permission | None:
        for p in self._permissions.values():
            if p.uuid == uuid:
                return p
        return None

    async def list_permissions(self, pagination: PaginationParams = PaginationParams()) -> tuple[list[Permission], int]:
        filtered = list(self._permissions.values())
        total = len(filtered)
        return filtered[pagination.offset : pagination.offset + pagination.limit], total

    # Roles

    async def create_role(self, role: Role) -> Role:
        role.id = self._next_role_id
        self._next_role_id += 1
        role.uuid = str(uuid_utils.uuid7())
        self._roles[role.id] = role
        self._role_permissions[role.id] = set()
        return role

    async def get_role_by_name(self, name: str) -> Role | None:
        for r in self._roles.values():
            if r.name == name:
                return r
        return None

    async def get_role_by_uuid(self, uuid: str) -> Role | None:
        for r in self._roles.values():
            if r.uuid == uuid:
                if r.id is None:
                    continue
                # Hydrate permissions
                perm_ids = self._role_permissions.get(r.id, set())
                r.permissions = [self._permissions[pid] for pid in perm_ids if pid in self._permissions]
                return r
        return None

    async def list_roles(self, pagination: PaginationParams = PaginationParams()) -> tuple[list[Role], int]:
        filtered = list(self._roles.values())
        total = len(filtered)
        return filtered[pagination.offset : pagination.offset + pagination.limit], total

    # Role <-> Permission

    async def assign_permission_to_role(self, role_id: int, permission_id: int, assigned_by: int | None = None) -> None:
        if role_id not in self._role_permissions:
            self._role_permissions[role_id] = set()
        self._role_permissions[role_id].add(permission_id)
        self._role_permission_meta[(role_id, permission_id)] = {
            "assigned_by": assigned_by,
            "assigned_at": datetime.now(UTC),
        }

    async def remove_permission_from_role(self, role_id: int, permission_id: int) -> None:
        if role_id in self._role_permissions:
            self._role_permissions[role_id].discard(permission_id)
        self._role_permission_meta.pop((role_id, permission_id), None)

    async def get_role_permissions(self, role_id: int) -> list[Permission]:
        perm_ids = self._role_permissions.get(role_id, set())
        return [self._permissions[pid] for pid in perm_ids if pid in self._permissions]

    # User <-> Role

    async def assign_role_to_user(self, user_id: int, role_id: int, assigned_by: int | None = None) -> None:
        if user_id not in self._user_roles:
            self._user_roles[user_id] = set()
        self._user_roles[user_id].add(role_id)
        self._user_role_meta[(user_id, role_id)] = {"assigned_by": assigned_by, "assigned_at": datetime.now(UTC)}

    async def remove_role_from_user(self, user_id: int, role_id: int) -> None:
        if user_id in self._user_roles:
            self._user_roles[user_id].discard(role_id)
        self._user_role_meta.pop((user_id, role_id), None)

    async def get_user_roles(self, user_id: int) -> list[Role]:
        role_ids = self._user_roles.get(user_id, set())
        roles = []
        for rid in role_ids:
            role = self._roles.get(rid)
            if role and role.id is not None:
                perm_ids = self._role_permissions.get(role.id, set())
                role.permissions = [self._permissions[pid] for pid in perm_ids if pid in self._permissions]
                roles.append(role)
        return roles

    async def get_user_permissions(self, user_id: int) -> list[Permission]:
        role_ids = self._user_roles.get(user_id, set())
        seen: set[int] = set()
        permissions = []
        for rid in role_ids:
            for pid in self._role_permissions.get(rid, set()):
                if pid not in seen and pid in self._permissions:
                    seen.add(pid)
                    permissions.append(self._permissions[pid])
        return permissions

    async def user_has_permission(self, user_id: int, permission_name: str) -> bool:
        perms = await self.get_user_permissions(user_id)
        return any(p.name == permission_name for p in perms)

    async def user_has_role(self, user_id: int, role_name: str) -> bool:
        roles = await self.get_user_roles(user_id)
        return any(r.name == role_name for r in roles)

    async def get_user_ids_for_role(self, role_id: int) -> list[int]:
        user_ids = []
        for uid, role_ids in self._user_roles.items():
            if role_id in role_ids:
                user_ids.append(uid)
        return user_ids

    async def get_user_role_assignments(self, user_id: int) -> list[UserRoleAssignment]:
        role_ids = self._user_roles.get(user_id, set())
        assignments = []
        for rid in role_ids:
            role = self._roles.get(rid)
            if role:
                meta = self._user_role_meta.get((user_id, rid), {})
                assignments.append(
                    UserRoleAssignment(
                        role=role, assigned_by=meta.get("assigned_by"), assigned_at=meta.get("assigned_at")
                    )
                )
        return assignments

    async def get_role_permission_assignments(self, role_id: int) -> list[RolePermissionAssignment]:
        perm_ids = self._role_permissions.get(role_id, set())
        assignments = []
        for pid in perm_ids:
            perm = self._permissions.get(pid)
            if perm:
                meta = self._role_permission_meta.get((role_id, pid), {})
                assignments.append(
                    RolePermissionAssignment(
                        permission=perm, assigned_by=meta.get("assigned_by"), assigned_at=meta.get("assigned_at")
                    )
                )
        return assignments


@pytest.fixture
def rbac_repo() -> InMemoryRbacRepository:
    return InMemoryRbacRepository()
