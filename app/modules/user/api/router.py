from fastapi import APIRouter, Depends, Query

from app.core.auth import require_permission
from app.core.exceptions import AppException
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PaginationParams
from app.core.rate_limit import rate_limit
from app.core.response import CleanRoute, ErrorEnvelope, SuccessEnvelope
from app.modules.user.api.dependencies import (
    get_delete_use_case,
    get_list_users_use_case,
    get_prune_use_case,
    get_register_use_case,
    get_restore_user_use_case,
    get_update_status_use_case,
    get_user_query_use_case,
)
from app.modules.user.api.schemas import RegisterRequest, UpdateUserStatusRequest, UserListResponse, UserResponse
from app.modules.user.cqrs.command import (
    DeleteUserCommand,
    PruneUserCommand,
    RegisterUserCommand,
    RestoreUserByUuidCommand,
    UpdateUserStatusCommand,
)
from app.modules.user.cqrs.query import GetUserByEmailQuery, GetUserByUsernameQuery, GetUserByUuidQuery, ListUsersQuery
from app.modules.user.domain.entities import UserStatus
from app.modules.user.domain.exception import (
    CannotUpdateToInactiveError,
    InvalidPhoneNumberError,
    PasswordsDoNotMatchError,
    UserAlreadyExistsError,
    UserNotDeletedError,
    UserNotFoundError,
    WeakPasswordError,
)
from app.modules.user.use_cases.delete_user import DeleteUserUseCase
from app.modules.user.use_cases.get_user import GetUserUseCase
from app.modules.user.use_cases.list_users import ListUsersUseCase
from app.modules.user.use_cases.prune_user import PruneUserUseCase
from app.modules.user.use_cases.register_user import RegisterUserUseCase
from app.modules.user.use_cases.restore_user import RestoreUserUseCase
from app.modules.user.use_cases.update_user_status import UpdateUserStatusUseCase

router = APIRouter(prefix="/users", tags=["users"], route_class=CleanRoute)


# Maps domain exceptions to machine-readable error codes and HTTP statuses.
# Used by _map_error() to convert domain exceptions to AppException.
DOMAIN_TO_APP = {
    UserAlreadyExistsError: ("USER_ALREADY_EXISTS", 409),
    UserNotFoundError: ("USER_NOT_FOUND", 404),
    PasswordsDoNotMatchError: ("PASSWORDS_DO_NOT_MATCH", 422),
    WeakPasswordError: ("WEAK_PASSWORD", 422),
    InvalidPhoneNumberError: ("INVALID_PHONE_NUMBER", 422),
    CannotUpdateToInactiveError: ("CANNOT_UPDATE_TO_INACTIVE", 422),
    UserNotDeletedError: ("USER_NOT_DELETED", 422),
}


def _map_error(exc: Exception) -> AppException:
    exc_class = type(exc)
    if exc_class in DOMAIN_TO_APP:
        code, status = DOMAIN_TO_APP[exc_class]
        return AppException(code=code, status_code=status, detail=str(exc))
    return AppException(code="UNKNOWN_ERROR", status_code=500, detail=str(exc))


@router.post(
    "/register",
    response_model=SuccessEnvelope[UserResponse],
    status_code=201,
    responses={
        409: {"model": ErrorEnvelope, "description": "Email already taken"},
        422: {"model": ErrorEnvelope, "description": "Validation error (password, phone, or passwords don't match)"},
        429: {"model": ErrorEnvelope, "description": "Too many requests"},
    },
    summary="Register a new user",
    dependencies=[Depends(rate_limit(3, 300))],
)
async def register(
    request: RegisterRequest, use_case: RegisterUserUseCase = Depends(get_register_use_case)
) -> SuccessEnvelope[UserResponse]:
    """Create a new user account.

    Validates the email, checks for duplicates, hashes the password
    with Argon2id, persists the user, and publishes a UserRegisteredEvent.
    """
    command = RegisterUserCommand(
        email=request.email,
        password=request.password,
        password2=request.password2,
        username=request.username,
        phone_number=request.phone_number,
        first_name=request.first_name,
        last_name=request.last_name,
    )
    try:
        result = await use_case.execute(command)
    except (UserAlreadyExistsError, PasswordsDoNotMatchError, WeakPasswordError, InvalidPhoneNumberError) as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=201, data=UserResponse.from_entity(result.user))


@router.patch(
    "/{uuid}/status",
    response_model=SuccessEnvelope[UserResponse],
    responses={
        404: {"model": ErrorEnvelope, "description": "User not found"},
        422: {"model": ErrorEnvelope, "description": "Cannot set inactive status"},
        403: {"model": ErrorEnvelope, "description": "Permission denied"},
    },
    summary="Update user status",
    dependencies=[Depends(require_permission("user:update"))],
)
async def update_status(
    uuid: str, request: UpdateUserStatusRequest, use_case: UpdateUserStatusUseCase = Depends(get_update_status_use_case)
) -> SuccessEnvelope[UserResponse]:
    """Update a user's account status.

    Allowed transitions: any valid status except **inactive**.
    Use the DELETE endpoint to deactivate a user.
    """
    command = UpdateUserStatusCommand(uuid=uuid, new_status=request.status.value)
    try:
        result = await use_case.execute(command)
    except (UserNotFoundError, CannotUpdateToInactiveError) as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=200, data=UserResponse.from_entity(result.user))


@router.delete(
    "/{uuid}",
    response_model=SuccessEnvelope[UserResponse],
    responses={
        404: {"model": ErrorEnvelope, "description": "User not found"},
        403: {"model": ErrorEnvelope, "description": "Permission denied"},
    },
    summary="Soft delete a user",
    dependencies=[Depends(require_permission("user:delete"))],
)
async def delete_user(
    uuid: str, use_case: DeleteUserUseCase = Depends(get_delete_use_case)
) -> SuccessEnvelope[UserResponse]:
    """Soft-delete a user by setting their status to **inactive**
    and recording the deletion timestamp in `deleted_at`.
    """
    command = DeleteUserCommand(uuid=uuid)
    try:
        result = await use_case.execute(command)
    except UserNotFoundError as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=200, data=UserResponse.from_entity(result.user))


@router.delete(
    "/{uuid}/prune",
    response_model=SuccessEnvelope[UserResponse],
    responses={
        404: {"model": ErrorEnvelope, "description": "User not found"},
        403: {"model": ErrorEnvelope, "description": "Permission denied"},
    },
    summary="Permanently delete a user",
    dependencies=[Depends(require_permission("user:delete"))],
)
async def prune_user(
    uuid: str, use_case: PruneUserUseCase = Depends(get_prune_use_case)
) -> SuccessEnvelope[UserResponse]:
    """Permanently remove a user from the database.

    This action cannot be undone. Use the soft-delete endpoint
    for reversible deletions.
    """
    command = PruneUserCommand(uuid=uuid)
    try:
        result = await use_case.execute(command)
    except UserNotFoundError as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=200, data=UserResponse.from_entity(result.user))


@router.get(
    "/by-uuid/{uuid}",
    response_model=SuccessEnvelope[UserResponse],
    responses={
        404: {"model": ErrorEnvelope, "description": "User not found"},
        403: {"model": ErrorEnvelope, "description": "Permission denied"},
    },
    summary="Get user by UUID",
    dependencies=[Depends(require_permission("user:read"))],
)
async def get_by_uuid(
    uuid: str, use_case: GetUserUseCase = Depends(get_user_query_use_case)
) -> SuccessEnvelope[UserResponse]:
    """Look up a user by their UUID v7 identifier."""
    command = GetUserByUuidQuery(uuid=uuid)
    try:
        user = await use_case.by_uuid(command)
    except UserNotFoundError as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=200, data=UserResponse.from_entity(user))


@router.get(
    "/by-username/{username}",
    response_model=SuccessEnvelope[UserResponse],
    responses={
        404: {"model": ErrorEnvelope, "description": "User not found"},
        403: {"model": ErrorEnvelope, "description": "Permission denied"},
    },
    summary="Get user by username",
    dependencies=[Depends(require_permission("user:read"))],
)
async def get_by_username(
    username: str, use_case: GetUserUseCase = Depends(get_user_query_use_case)
) -> SuccessEnvelope[UserResponse]:
    """Look up a user by their unique username."""
    command = GetUserByUsernameQuery(username=username)
    try:
        user = await use_case.by_username(command)
    except UserNotFoundError as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=200, data=UserResponse.from_entity(user))


@router.get(
    "/by-email/{email}",
    response_model=SuccessEnvelope[UserResponse],
    responses={
        404: {"model": ErrorEnvelope, "description": "User not found"},
        403: {"model": ErrorEnvelope, "description": "Permission denied"},
    },
    summary="Get user by email",
    dependencies=[Depends(require_permission("user:read"))],
)
async def get_by_email(
    email: str, use_case: GetUserUseCase = Depends(get_user_query_use_case)
) -> SuccessEnvelope[UserResponse]:
    """Look up a user by their email address."""
    command = GetUserByEmailQuery(email=email)
    try:
        user = await use_case.by_email(command)
    except UserNotFoundError as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=200, data=UserResponse.from_entity(user))


@router.patch(
    "/by-uuid/{uuid}/restore",
    response_model=SuccessEnvelope[UserResponse],
    responses={
        404: {"model": ErrorEnvelope, "description": "User not found"},
        422: {"model": ErrorEnvelope, "description": "User was not deleted"},
        403: {"model": ErrorEnvelope, "description": "Permission denied"},
    },
    summary="Restore a soft-deleted user",
    dependencies=[Depends(require_permission("user:update"))],
)
async def restore_user(
    uuid: str, use_case: RestoreUserUseCase = Depends(get_restore_user_use_case)
) -> SuccessEnvelope[UserResponse]:
    """Restore a soft-deleted user by their UUID.

    Clears the `deleted_at` timestamp and resets the status
    to `pending_verification`.
    """
    command = RestoreUserByUuidCommand(uuid=uuid)
    try:
        result = await use_case.execute(command)
    except (UserNotFoundError, UserNotDeletedError) as e:
        raise _map_error(e) from e

    return SuccessEnvelope(statusCode=200, data=UserResponse.from_entity(result.user))


@router.get(
    "",
    response_model=SuccessEnvelope[UserListResponse],
    responses={403: {"model": ErrorEnvelope, "description": "Permission denied"}},
    summary="List all users",
    dependencies=[Depends(require_permission("user:read"))],
)
async def list_users(
    status: UserStatus | None = Query(default=None, description="Filter by status."),
    include_deleted: bool = Query(default=False, description="Include soft-deleted users in the results."),
    offset: int = Query(default=0, ge=0, description="Number of records to skip for pagination."),
    limit: int = Query(
        default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Maximum number of records to return."
    ),
    use_case: ListUsersUseCase = Depends(get_list_users_use_case),
) -> SuccessEnvelope[UserListResponse]:
    """Retrieve a paginated list of users.

    Supports optional filtering by status and soft-deleted state.
    Excludes soft-deleted users by default.
    """
    command = ListUsersQuery(
        status=status.value if status else None,
        include_deleted=include_deleted,
        pagination=PaginationParams(offset=offset, limit=limit),
    )
    result = await use_case.execute(command)

    return SuccessEnvelope(
        statusCode=200,
        data=UserListResponse(
            items=[UserResponse.from_entity(u) for u in result.page.items],
            total=result.page.total,
            offset=result.page.offset,
            limit=result.page.limit,
        ),
    )
