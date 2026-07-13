from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import jwt as pyjwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import ICacheService, NullCache
from app.core.database import get_db
from app.core.event_bus import IEventBus
from app.core.jwt import JWTService
from app.modules.auth.domain.exception import (
    InvalidTokenError,
    PermissionDeniedError,
    TokenBlacklistedError,
    TokenExpiredError,
)
from app.modules.auth.use_cases.login import LoginUseCase
from app.modules.auth.use_cases.logout import LogoutUseCase
from app.modules.auth.use_cases.profile import GetProfileUseCase
from app.modules.auth.use_cases.refresh import RefreshTokenUseCase
from app.modules.otp.domain.interfaces import IOtpRepository
from app.modules.rbac.domain.interfaces import IRbacRepository
from app.modules.rbac.infrastructure.persistence.repository import SQLAlchemyRbacRepository
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.interfaces import IUserRepository
from app.modules.user.infrastructure.persistence.repository import SQLAlchemyUserRepository

security = HTTPBearer(auto_error=True)
optional_security = HTTPBearer(auto_error=False)


def get_jwt_service() -> JWTService:
    """Dependency provider for ``JWTService``.

    Returns:
        A ``JWTService`` instance configured via settings defaults.
    """
    return JWTService()


def get_cache_service(request: Request) -> ICacheService:
    """Dependency provider for the application's cache service.

    Retrieves the ``ICacheService`` instance stored on ``app.state``
    during application startup. Falls back to ``NullCache`` if not set.

    Args:
        request: The incoming HTTP request.

    Returns:
        Either a ``RedisCache`` or ``NullCache`` instance.
    """
    return getattr(request.app.state, "cache_service", NullCache())


def get_event_bus(request: Request) -> IEventBus:
    """Dependency provider for the application's event bus.

    Args:
        request: The incoming HTTP request.

    Returns:
        The ``InMemoryEventBus`` instance stored on ``app.state``.
    """
    return cast(IEventBus, request.app.state.event_bus)


async def get_user_repo(db: AsyncSession = Depends(get_db)) -> IUserRepository:
    """Dependency provider for the user repository.

    Args:
        db: An async SQLAlchemy session.

    Returns:
        A ``SQLAlchemyUserRepository`` bound to the session.
    """
    return SQLAlchemyUserRepository(db)


async def get_rbac_repo(db: AsyncSession = Depends(get_db)) -> IRbacRepository:
    """Dependency provider for the RBAC repository.

    Args:
        db: An async SQLAlchemy session.

    Returns:
        A ``SQLAlchemyRbacRepository`` bound to the session.
    """
    return SQLAlchemyRbacRepository(db)


async def get_login_use_case(
    repo: IUserRepository = Depends(get_user_repo),
    cache: ICacheService = Depends(get_cache_service),
    jwt: JWTService = Depends(get_jwt_service),
    event_bus: IEventBus = Depends(get_event_bus),
) -> LoginUseCase:
    """Dependency provider for ``LoginUseCase``.

    Wires together the user repository, cache, JWT service, and event bus.
    """
    return LoginUseCase(user_repo=repo, cache=cache, jwt=jwt, event_bus=event_bus)


async def get_refresh_use_case(
    jwt: JWTService = Depends(get_jwt_service),
    cache: ICacheService = Depends(get_cache_service),
    event_bus: IEventBus = Depends(get_event_bus),
    repo: IUserRepository = Depends(get_user_repo),
) -> RefreshTokenUseCase:
    """Dependency provider for ``RefreshTokenUseCase``.

    Wires together the JWT service, cache, event bus, and user repository.
    """
    return RefreshTokenUseCase(jwt=jwt, cache=cache, event_bus=event_bus, user_repo=repo)


async def get_logout_use_case(
    jwt: JWTService = Depends(get_jwt_service),
    cache: ICacheService = Depends(get_cache_service),
    event_bus: IEventBus = Depends(get_event_bus),
) -> LogoutUseCase:
    """Dependency provider for ``LogoutUseCase``.

    Wires together the JWT service, cache, and event bus.
    """
    return LogoutUseCase(jwt=jwt, cache=cache, event_bus=event_bus)


async def get_profile_use_case(
    repo: IUserRepository = Depends(get_user_repo), cache: ICacheService = Depends(get_cache_service)
) -> GetProfileUseCase:
    return GetProfileUseCase(user_repo=repo, cache=cache)


if TYPE_CHECKING:
    from app.modules.auth.use_cases.activate_account import ActivateAccountUseCase
    from app.modules.auth.use_cases.send_activation_otp import SendActivationOtpUseCase


async def get_otp_repo(db: AsyncSession = Depends(get_db)) -> IOtpRepository:
    from app.modules.otp.infrastructure.persistence.repository import SQLAlchemyOtpRepository

    return SQLAlchemyOtpRepository(db)


async def get_send_activation_otp_use_case(
    user_repo: IUserRepository = Depends(get_user_repo),
    otp_repo: IOtpRepository = Depends(get_otp_repo),
    cache: ICacheService = Depends(get_cache_service),
    event_bus: IEventBus = Depends(get_event_bus),
) -> SendActivationOtpUseCase:
    from app.modules.auth.use_cases.send_activation_otp import SendActivationOtpUseCase

    return SendActivationOtpUseCase(user_repo=user_repo, otp_repo=otp_repo, cache=cache, event_bus=event_bus)


async def get_activate_account_use_case(
    user_repo: IUserRepository = Depends(get_user_repo),
    otp_repo: IOtpRepository = Depends(get_otp_repo),
    cache: ICacheService = Depends(get_cache_service),
    event_bus: IEventBus = Depends(get_event_bus),
) -> ActivateAccountUseCase:
    from app.modules.auth.use_cases.activate_account import ActivateAccountUseCase

    return ActivateAccountUseCase(user_repo=user_repo, otp_repo=otp_repo, cache=cache, event_bus=event_bus)


async def require_authenticated(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    jwt_service: JWTService = Depends(get_jwt_service),
    cache: ICacheService = Depends(get_cache_service),
) -> str:
    """Require a valid access token and return the authenticated user's UUID.

    Validates the token cryptographically, checks the token type, and
    verifies the token has not been blacklisted (e.g. via logout).
    Does NOT check account status — use ``require_authenticated_user`` for that.

    Args:
        credentials: The parsed Bearer token from the ``Authorization`` header.
        jwt_service: JWT service for token verification.
        cache: Cache service for blacklist lookup.

    Returns:
        The authenticated user's UUID as a string.

    Raises:
        InvalidTokenError: Token is malformed, wrong type, or expired.
        TokenExpiredError: The access token has expired.
        TokenBlacklistedError: The access token has been revoked via logout.
    """
    token = credentials.credentials
    try:
        payload = jwt_service.decode(token)
    except pyjwt.ExpiredSignatureError:
        raise TokenExpiredError("Access token has expired.") from None
    except pyjwt.InvalidTokenError:
        raise InvalidTokenError("Invalid access token.") from None

    if payload.get("type") != "access":
        raise InvalidTokenError("Token is not an access token.")

    jti = payload["jti"]
    if await cache.exists(f"token:blacklist:{jti}"):
        raise TokenBlacklistedError("Access token has been revoked.")

    return cast(str, payload["sub"])


async def require_authenticated_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    jwt_service: JWTService = Depends(get_jwt_service),
    repo: IUserRepository = Depends(get_user_repo),
    cache: ICacheService = Depends(get_cache_service),
) -> User:
    """Require an active, authenticated user and return the ``User`` domain entity.

    Extracts the ``Authorization: Bearer <token>`` header, decodes the
    access token, checks the blacklist, looks up the user by UUID, and
    returns the domain entity. Also verifies the account is active (not
    suspended or inactive). Use this dependency on any protected route
    that needs the full user.

    Args:
        credentials: The parsed Bearer token from the ``Authorization`` header.
        jwt_service: JWT service for token verification.
        repo: User repository for user lookup.
        cache: Cache service for blacklist lookup.

    Returns:
        The authenticated ``User`` domain entity.

    Raises:
        InvalidTokenError: Token is malformed, wrong type, user not found, or account is suspended/inactive.
        TokenExpiredError: The access token has expired.
        TokenBlacklistedError: The access token has been revoked via logout.
    """
    token = credentials.credentials
    try:
        payload = jwt_service.decode(token)
    except pyjwt.ExpiredSignatureError:
        raise TokenExpiredError("Access token has expired.") from None
    except pyjwt.InvalidTokenError:
        raise InvalidTokenError("Invalid access token.") from None

    if payload.get("type") != "access":
        raise InvalidTokenError("Token is not an access token.")

    jti = payload["jti"]
    if await cache.exists(f"token:blacklist:{jti}"):
        raise TokenBlacklistedError("Access token has been revoked.")

    user_uuid = cast(str, payload["sub"])
    user = await repo.get_by_uuid(user_uuid)
    if not user:
        raise InvalidTokenError("User not found.")

    if user.status == UserStatus.SUSPENDED:
        raise InvalidTokenError("Account is suspended.")
    if user.status == UserStatus.INACTIVE:
        raise InvalidTokenError("Account is deactivated.")

    return user


def require_permission(permission: str) -> Callable[..., Any]:
    """Factory that returns a FastAPI dependency enforcing a specific permission.

    Usage::

        @router.post("/users", dependencies=[Depends(require_permission("user:create"))])
        async def create_user(...):
            ...

    Superusers bypass all permission checks automatically.

    Permission lookups are cached per-user for 5 minutes to avoid
    hitting the database on every protected request.
    """

    async def _dependency(
        user: User = Depends(require_authenticated_user),
        rbac_repo: IRbacRepository = Depends(get_rbac_repo),
        cache: ICacheService = Depends(get_cache_service),
    ) -> User:
        if user.is_superuser:
            return user

        if user.id is None:
            raise InvalidTokenError("User identifier is missing.")

        cache_key = f"user_permissions:{user.id}"
        cached_perms = await cache.get(cache_key)

        if cached_perms is not None:
            has_perm = permission in cached_perms
        else:
            perms = await rbac_repo.get_user_permissions(user.id)
            perm_names = [p.name for p in perms]
            await cache.set(cache_key, perm_names, ttl=300)
            has_perm = permission in perm_names

        if not has_perm:
            raise PermissionDeniedError(f"Permission '{permission}' required.")
        return user

    return _dependency
