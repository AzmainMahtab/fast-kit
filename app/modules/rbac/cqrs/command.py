from dataclasses import dataclass


@dataclass(frozen=True)
class CreatePermissionCommand:
    name: str
    description: str | None = None
    resource: str = ""
    action: str = ""


@dataclass(frozen=True)
class CreateRoleCommand:
    name: str
    description: str | None = None


@dataclass(frozen=True)
class AssignRoleCommand:
    user_id: int
    role_uuid: str
    assigned_by: int | None = None


@dataclass(frozen=True)
class RevokeRoleCommand:
    user_id: int
    role_uuid: str


@dataclass(frozen=True)
class AssignPermissionToRoleCommand:
    role_uuid: str
    permission_uuid: str
    assigned_by: int | None = None


@dataclass(frozen=True)
class RevokePermissionFromRoleCommand:
    role_uuid: str
    permission_uuid: str
