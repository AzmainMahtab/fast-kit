from app.core.cache import ICacheService
from app.core.event_bus import IEventBus
from app.core.hasher import get_password_hash, need_to_rehash, verify_password
from app.core.jwt import JWTService
from app.modules.auth.cqrs.command import LoginCommand
from app.modules.auth.cqrs.result import LoginResult
from app.modules.auth.domain.events import UserLoggedInEvent
from app.modules.auth.domain.exception import AccountSuspendedError, InvalidCredentialsError
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.interfaces import IUserRepository
from app.modules.user.domain.value_objects import Email, HashedPassword

CACHE_TTL = 300


class LoginUseCase:
    """Authenticate a user with email/password and issue JWT tokens.

    Performs credential verification via Argon2id, caches user data in
    Redis for 5 minutes to accelerate subsequent logins, and optionally
    rehashes the password if Argon2 parameters have changed.
    """

    def __init__(self, user_repo: IUserRepository, cache: ICacheService, jwt: JWTService, event_bus: IEventBus):
        self._user_repo = user_repo
        self._cache = cache
        self._jwt = jwt
        self._event_bus = event_bus

    async def execute(self, command: LoginCommand) -> LoginResult:
        """Verify credentials and return a token pair.

        Args:
            command: The login credentials.

        Returns:
            A ``LoginResult`` containing the token pair.

        Raises:
            InvalidCredentialsError: Email not found or password mismatch.
            AccountSuspendedError: User account is suspended.
        """
        user = await self._get_user(command.email)

        if user.status == UserStatus.SUSPENDED:
            raise AccountSuspendedError("Account is suspended.")
        if user.status == UserStatus.INACTIVE:
            raise InvalidCredentialsError("Account is deactivated.")

        if not verify_password(command.password, user.hashed_password.value):
            raise InvalidCredentialsError("Invalid email or password.")

        if need_to_rehash(user.hashed_password.value):
            user.update_password_hash(HashedPassword(get_password_hash(command.password)))
            await self._user_repo.update(user)

        await self._cache_login(command.email, user)

        tokens = self._jwt.create_token_pair(str(user.uuid))
        await self._event_bus.publish(UserLoggedInEvent(user_uuid=str(user.uuid), email=command.email))

        return LoginResult(access_token=tokens["access_token"], refresh_token=tokens["refresh_token"])

    async def _get_user(self, email: str) -> User:
        """Resolve a user by email, checking the cache first.

        Uses a Redis cache key ``auth:credentials:{email}`` to avoid
        a database lookup for users who log in frequently.
        """
        cached = await self._cache.get(f"auth:credentials:{email}")
        if cached:
            return User(
                uuid=cached.get("uuid"),
                email=Email(email),
                hashed_password=HashedPassword(cached["hashed_password"]),
                status=UserStatus(cached["status"]),
                username=cached.get("username", ""),
            )
        email_vo = Email(email)
        user = await self._user_repo.get_by_email(email_vo)
        if not user:
            raise InvalidCredentialsError("Invalid email or password.")
        return user

    async def _cache_login(self, email: str, user: User) -> None:
        """Cache the user's credential data after a successful login.

        Args:
            email: The user's email (used as cache key).
            user: The authenticated user entity.
        """
        await self._cache.set(
            f"auth:credentials:{email}",
            {
                "uuid": user.uuid,
                "hashed_password": user.hashed_password.value,
                "status": user.status.value,
                "username": user.username,
            },
            CACHE_TTL,
        )
