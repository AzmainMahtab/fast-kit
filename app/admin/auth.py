"""Admin authentication: session-cookie login backed by existing auth + RBAC.

Two layers, kept separate for testability:

- ``AdminAuthenticator`` — the verification logic. Depends only on the
  repository interfaces and the cache, so it is unit-testable with
  in-memory doubles and no database.
- ``AdminAuthBackend`` — the thin SQLAdmin adapter. Builds repositories
  from a session per request and delegates to ``AdminAuthenticator``.

Sessions are signed cookies (Starlette ``SessionMiddleware`` via SQLAdmin).
They are independent of the stateless API JWTs, which is deliberate: API
access tokens expire after 15 minutes, which would make admin sessions
unusable.
"""

from collections.abc import Callable

from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.admin.permissions import has_admin_access
from app.core.cache import ICacheService
from app.core.database import AsyncSessionLocal
from app.core.hasher import verify_password
from app.core.settings import settings
from app.modules.rbac.domain.interfaces import IRbacRepository
from app.modules.rbac.infrastructure.persistence.repository import SQLAlchemyRbacRepository
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.interfaces import IUserRepository
from app.modules.user.domain.value_objects import Email
from app.modules.user.infrastructure.persistence.repository import SQLAlchemyUserRepository

SESSION_USER_UUID_KEY = "admin_user_uuid"


class AdminAuthenticator:
    """Credential and session verification for the back-office.

    Depends only on repository interfaces and the cache service, so unit
    tests can inject in-memory doubles without a database.
    """

    def __init__(self, user_repo: IUserRepository, rbac_repo: IRbacRepository, cache: ICacheService):
        self._user_repo = user_repo
        self._rbac_repo = rbac_repo
        self._cache = cache

    async def verify_login(self, email: str, password: str) -> User | None:
        """Verify email/password credentials and admin access.

        Returns:
            The ``User`` entity when credentials are valid, the account is
            active, and the user may access the admin; otherwise ``None``.
        """
        try:
            user = await self._user_repo.get_by_email(Email(email))
        except ValueError:
            return None  # malformed email input
        if not user:
            return None
        return await self._verify_active_user_with_access(user, password)

    async def verify_session(self, user_uuid: str) -> User | None:
        """Re-verify an existing admin session on each request.

        Ensures the user still exists, is still active, and still holds
        admin access (permission revocation takes effect without waiting
        for the session to expire).
        """
        user = await self._user_repo.get_by_uuid(user_uuid)
        if not user:
            return None
        return await self._verify_active_user_with_access(user, password=None)

    async def _verify_active_user_with_access(self, user: User, password: str | None) -> User | None:
        if user.status != UserStatus.ACTIVE:
            return None
        if password is not None and not verify_password(password, user.hashed_password.value):
            return None
        if not await has_admin_access(user, self._rbac_repo, self._cache):
            return None
        return user


# Factory type: builds an authenticator from a database session.
AuthenticatorFactory = Callable[[AsyncSession], AdminAuthenticator]


def _default_authenticator_factory(session: AsyncSession, cache: ICacheService) -> AdminAuthenticator:
    return AdminAuthenticator(
        user_repo=SQLAlchemyUserRepository(session), rbac_repo=SQLAlchemyRbacRepository(session), cache=cache
    )


class AdminAuthBackend(AuthenticationBackend):
    """SQLAdmin authentication backend using signed session cookies.

    The SQLAdmin login form posts ``username`` and ``password`` fields;
    ``username`` is treated as the user's email.
    """

    def __init__(
        self,
        secret_key: str | None = None,
        session_factory: Callable[[], AsyncSession] = AsyncSessionLocal,
        authenticator_factory: Callable[
            [AsyncSession, ICacheService], AdminAuthenticator
        ] = _default_authenticator_factory,
        cache_getter: Callable[[], ICacheService | None] | None = None,
        **session_kwargs: object,
    ) -> None:
        super().__init__(secret_key=secret_key or settings.JWT_SECRET_KEY, **session_kwargs)
        self._session_factory = session_factory
        self._authenticator_factory = authenticator_factory
        self._cache_getter = cache_getter

    def _resolve_cache(self, request: Request) -> ICacheService | None:
        """Resolve the security cache. Fail closed when unavailable (same policy as the API).

        Note: inside SQLAdmin's mounted sub-application ``request.app`` is the
        *admin sub-app*, not the FastAPI app, so the cache cannot reliably be
        read from ``request.app.state``. ``create_admin`` injects a
        ``cache_getter`` closure bound to the real app instead.
        """
        if self._cache_getter is not None:
            return self._cache_getter()
        return getattr(request.app.state, "security_cache_service", None)

    async def login(self, request: Request) -> bool:
        cache = self._resolve_cache(request)
        if cache is None:
            return False  # fail closed

        form = await request.form()
        email = str(form.get("username", ""))
        password = str(form.get("password", ""))
        if not email or not password:
            return False

        async with self._session_factory() as session:
            authenticator = self._authenticator_factory(session, cache)
            user = await authenticator.verify_login(email, password)

        if not user or not user.uuid:
            return False

        request.session.update({SESSION_USER_UUID_KEY: str(user.uuid)})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        cache = self._resolve_cache(request)
        if cache is None:
            return False  # fail closed

        user_uuid = request.session.get(SESSION_USER_UUID_KEY)
        if not user_uuid:
            return False

        async with self._session_factory() as session:
            authenticator = self._authenticator_factory(session, cache)
            user = await authenticator.verify_session(str(user_uuid))

        return user is not None
