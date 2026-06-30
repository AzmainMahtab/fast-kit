from fastapi import APIRouter, Depends, Query

from app.core.auth import require_authenticated_user
from app.core.exceptions import AppException
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PaginationParams
from app.core.response import CleanRoute, ErrorEnvelope, SuccessEnvelope
from app.modules.rbac.api.dependencies import (
    get_assign_permission_use_case,
    get_assign_role_use_case,
    get_check_permission_use_case,
    get_create_permission_use_case,
    get_create_role_use_case,
    get_get_role_use_case,
    get_get_user_permissions_use_case,
    get_get_user_roles_use_case,
    get_list_permissions_use_case,
    get_list_roles_use_case,
    get_revoke_permission_use_case,
    get_revoke_role_use_case,
)
from app.modules.rbac.api.schemas import (
    AssignPermissionRequest,
    AssignRoleRequest,
    CreatePermissionRequest,
    CreateRoleRequest,
    PermissionListResponse,
    PermissionResponse,
    RevokePermissionRequest,
    RevokeRoleRequest,
    RoleListResponse,
    RoleResponse,
    UserPermissionsResponse,
    UserRolesResponse,
)
from app.modules.rbac.cqrs.command import (
    AssignPermissionToRoleCommand,
    AssignRoleCommand,
    CreatePermissionCommand,
    CreateRoleCommand,
    RevokePermissionFromRoleCommand,
    RevokeRoleCommand,
)
from app.modules.rbac.cqrs.query import (
    CheckUserPermissionQuery,
    GetRoleByUuidQuery,
    GetUserPermissionsQuery,
    GetUserRolesQuery,
    ListPermissionsQuery,
    ListRolesQuery,
)
from app.modules.rbac.domain.exception import (
    RBAC_EXCEPTIONS,
    PermissionAlreadyAssignedError,
    PermissionAlreadyExistsError,
    PermissionNotFoundError,
    RoleAlreadyAssignedError,
    RoleAlreadyExistsError,
    RoleNotAssignedError,
    RoleNotFoundError,
)
from app.modules.rbac.use_cases.assign_permission import AssignPermissionToRoleUseCase
from app.modules.rbac.use_cases.assign_role import AssignRoleUseCase
from app.modules.rbac.use_cases.check_permission import CheckPermissionUseCase
from app.modules.rbac.use_cases.create_permission import CreatePermissionUseCase
from app.modules.rbac.use_cases.create_role import CreateRoleUseCase
from app.modules.rbac.use_cases.get_role import GetRoleUseCase
from app.modules.rbac.use_cases.get_user_permissions import GetUserPermissionsUseCase
from app.modules.rbac.use_cases.get_user_roles import GetUserRolesUseCase
from app.modules.rbac.use_cases.list_permissions import ListPermissionsUseCase
from app.modules.rbac.use_cases.list_roles import ListRolesUseCase
from app.modules.rbac.use_cases.revoke_permission import RevokePermissionFromRoleUseCase
from app.modules.rbac.use_cases.revoke_role import RevokeRoleUseCase

router = APIRouter(prefix="/rbac", tags=["rbac"], route_class=CleanRoute)


def _map_rbac_error(exc: Exception) -> AppException:
    exc_class = type(exc)
    if exc_class in RBAC_EXCEPTIONS:
        code, status = RBAC_EXCEPTIONS[exc_class]
        return AppException(code=code, status_code=status, detail=str(exc))
    return AppException(code="UNKNOWN_ERROR", status_code=500, detail=str(exc))


# Permissions

@router.post(
    "/permissions",
    response_model=SuccessEnvelope[PermissionResponse],
    status_code=201,
    responses={
        409: {"model": ErrorEnvelope, "description": "Permission already exists"},
    },
    summary="Create a new permission",
)
async def create_permission(
    request: CreatePermissionRequest,
    use_case: CreatePermissionUseCase = Depends(get_create_permission_use_case),
):
    command = CreatePermissionCommand(
        name=request.name,
        description=request.description,
        resource=request.resource,
        action=request.action,
    )
    try:
        result = await use_case.execute(command)
    except PermissionAlreadyExistsError as e:
        raise _map_rbac_error(e) from e

    return SuccessEnvelope(statusCode=201, data=PermissionResponse.from_entity(result.permission))


@router.get(
    "/permissions",
    response_model=SuccessEnvelope[PermissionListResponse],
    summary="List all permissions",
)
async def list_permissions(
    offset: int = Query(default=0, ge=0, description="Number of records to skip for pagination."),
    limit: int = Query(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Maximum number of records to return."
    ),
    use_case: ListPermissionsUseCase = Depends(get_list_permissions_use_case),
):
    query = ListPermissionsQuery(pagination=PaginationParams(offset=offset, limit=limit))
    result = await use_case.execute(query)

    return SuccessEnvelope(
        statusCode=200,
        data=PermissionListResponse(
            items=[PermissionResponse.from_entity(p) for p in result.page.items],
            total=result.page.total,
            offset=result.page.offset,
            limit=result.page.limit,
        ),
    )


# Roles

@router.post(
    "/roles",
    response_model=SuccessEnvelope[RoleResponse],
    status_code=201,
    responses={
        409: {"model": ErrorEnvelope, "description": "Role already exists"},
    },
    summary="Create a new role",
)
async def create_role(
    request: CreateRoleRequest,
    use_case: CreateRoleUseCase = Depends(get_create_role_use_case),
):
    command = CreateRoleCommand(name=request.name, description=request.description)
    try:
        result = await use_case.execute(command)
    except RoleAlreadyExistsError as e:
        raise _map_rbac_error(e) from e

    return SuccessEnvelope(statusCode=201, data=RoleResponse.from_entity(result.role))


@router.get(
    "/roles",
    response_model=SuccessEnvelope[RoleListResponse],
    summary="List all roles",
)
async def list_roles(
    offset: int = Query(default=0, ge=0, description="Number of records to skip for pagination."),
    limit: int = Query(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Maximum number of records to return."
    ),
    use_case: ListRolesUseCase = Depends(get_list_roles_use_case),
):
    query = ListRolesQuery(pagination=PaginationParams(offset=offset, limit=limit))
    result = await use_case.execute(query)

    return SuccessEnvelope(
        statusCode=200,
        data=RoleListResponse(
            items=[RoleResponse.from_entity(r) for r in result.page.items],
            total=result.page.total,
            offset=result.page.offset,
            limit=result.page.limit,
        ),
    )


@router.get(
    "/roles/{uuid}",
    response_model=SuccessEnvelope[RoleResponse],
    responses={404: {"model": ErrorEnvelope, "description": "Role not found"}},
    summary="Get role by UUID",
)
async def get_role_by_uuid(
    uuid: str,
    use_case: GetRoleUseCase = Depends(get_get_role_use_case),
):
    query = GetRoleByUuidQuery(uuid=uuid)
    try:
        role = await use_case.by_uuid(query)
    except RoleNotFoundError as e:
        raise _map_rbac_error(e) from e

    return SuccessEnvelope(statusCode=200, data=RoleResponse.from_entity(role))


# Role <-> Permission

@router.post(
    "/roles/{role_uuid}/permissions",
    response_model=SuccessEnvelope[dict],
    responses={
        404: {"model": ErrorEnvelope, "description": "Role or permission not found"},
        409: {"model": ErrorEnvelope, "description": "Permission already assigned"},
    },
    summary="Assign a permission to a role",
)
async def assign_permission_to_role(
    role_uuid: str,
    request: AssignPermissionRequest,
    use_case: AssignPermissionToRoleUseCase = Depends(get_assign_permission_use_case),
    current_user=Depends(require_authenticated_user),
):
    command = AssignPermissionToRoleCommand(
        role_uuid=role_uuid,
        permission_uuid=request.permission_uuid,
        assigned_by=current_user.id,
    )
    try:
        await use_case.execute(command)
    except (RoleNotFoundError, PermissionNotFoundError, PermissionAlreadyAssignedError) as e:
        raise _map_rbac_error(e) from e

    return SuccessEnvelope(statusCode=200, data={"message": "Permission assigned to role."})


@router.delete(
    "/roles/{role_uuid}/permissions",
    response_model=SuccessEnvelope[dict],
    responses={
        404: {"model": ErrorEnvelope, "description": "Role or permission not found"},
    },
    summary="Revoke a permission from a role",
)
async def revoke_permission_from_role(
    role_uuid: str,
    request: RevokePermissionRequest,
    use_case: RevokePermissionFromRoleUseCase = Depends(get_revoke_permission_use_case),
):
    command = RevokePermissionFromRoleCommand(role_uuid=role_uuid, permission_uuid=request.permission_uuid)
    try:
        await use_case.execute(command)
    except (RoleNotFoundError, PermissionNotFoundError) as e:
        raise _map_rbac_error(e) from e

    return SuccessEnvelope(statusCode=200, data={"message": "Permission revoked from role."})


# User <-> Role

@router.post(
    "/roles/{role_uuid}/users",
    response_model=SuccessEnvelope[dict],
    responses={
        404: {"model": ErrorEnvelope, "description": "Role not found"},
        409: {"model": ErrorEnvelope, "description": "Role already assigned"},
    },
    summary="Assign a role to a user",
)
async def assign_role_to_user(
    role_uuid: str,
    request: AssignRoleRequest,
    use_case: AssignRoleUseCase = Depends(get_assign_role_use_case),
    current_user=Depends(require_authenticated_user),
):
    command = AssignRoleCommand(
        user_id=request.user_id,
        role_uuid=role_uuid,
        assigned_by=current_user.id,
    )
    try:
        await use_case.execute(command)
    except (RoleNotFoundError, RoleAlreadyAssignedError) as e:
        raise _map_rbac_error(e) from e

    return SuccessEnvelope(statusCode=200, data={"message": "Role assigned to user."})


@router.delete(
    "/roles/{role_uuid}/users",
    response_model=SuccessEnvelope[dict],
    responses={
        404: {"model": ErrorEnvelope, "description": "Role not found"},
        400: {"model": ErrorEnvelope, "description": "Role not assigned to user"},
    },
    summary="Revoke a role from a user",
)
async def revoke_role_from_user(
    role_uuid: str,
    request: RevokeRoleRequest,
    use_case: RevokeRoleUseCase = Depends(get_revoke_role_use_case),
):
    command = RevokeRoleCommand(user_id=request.user_id, role_uuid=role_uuid)
    try:
        await use_case.execute(command)
    except (RoleNotFoundError, RoleNotAssignedError) as e:
        raise _map_rbac_error(e) from e

    return SuccessEnvelope(statusCode=200, data={"message": "Role revoked from user."})


# User permissions / roles lookups

@router.get(
    "/users/{user_id}/permissions",
    response_model=SuccessEnvelope[UserPermissionsResponse],
    summary="Get all permissions for a user",
)
async def get_user_permissions(
    user_id: int,
    use_case: GetUserPermissionsUseCase = Depends(get_get_user_permissions_use_case),
):
    query = GetUserPermissionsQuery(user_id=user_id)
    result = await use_case.execute(query)
    return SuccessEnvelope(
        statusCode=200,
        data=UserPermissionsResponse(
            user_id=user_id,
            permissions=[p.name for p in result.permissions],
        ),
    )


@router.get(
    "/users/{user_id}/roles",
    response_model=SuccessEnvelope[UserRolesResponse],
    summary="Get all roles for a user",
)
async def get_user_roles(
    user_id: int,
    use_case: GetUserRolesUseCase = Depends(get_get_user_roles_use_case),
):
    query = GetUserRolesQuery(user_id=user_id)
    result = await use_case.execute(query)
    return SuccessEnvelope(
        statusCode=200,
        data=UserRolesResponse(
            user_id=user_id,
            roles=[r.name for r in result.roles],
        ),
    )


@router.get(
    "/users/{user_id}/check",
    response_model=SuccessEnvelope[dict],
    summary="Check if a user has a specific permission",
)
async def check_user_permission(
    user_id: int,
    permission: str = Query(description="Permission name to check (e.g. user:create)."),
    use_case: CheckPermissionUseCase = Depends(get_check_permission_use_case),
):
    query = CheckUserPermissionQuery(user_id=user_id, permission_name=permission)
    result = await use_case.execute(query)
    return SuccessEnvelope(
        statusCode=200,
        data={"has_permission": result.has_permission},
    )
