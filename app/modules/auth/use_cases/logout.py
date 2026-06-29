from datetime import UTC, datetime

import jwt as pyjwt

from app.core.cache import ICacheService
from app.core.event_bus import IEventBus
from app.core.jwt import JWTService
from app.modules.auth.cqrs.command import LogoutCommand
from app.modules.auth.cqrs.result import LogoutResult
from app.modules.auth.domain.events import UserLoggedOutEvent
from app.modules.auth.domain.exception import InvalidTokenError


class LogoutUseCase:
    """Revoke both a refresh token and an access token by adding their JTIs
    to the Redis blacklist.

    Both tokens are required. Expired tokens are silently skipped (they are
    already useless). Malformed tokens are rejected with ``InvalidTokenError``.
    """

    def __init__(self, jwt: JWTService, cache: ICacheService, event_bus: IEventBus):
        self._jwt = jwt
        self._cache = cache
        self._event_bus = event_bus

    async def execute(self, command: LogoutCommand) -> LogoutResult:
        """Blacklist the refresh token and the access token.

        Args:
            command: Contains the refresh token and access token to revoke.

        Returns:
            A ``LogoutResult`` confirming the operation.

        Raises:
            InvalidTokenError: Either token is malformed or of the wrong type.
        """
        # --- refresh token ---
        try:
            refresh_payload = self._jwt.decode(command.refresh_token)
        except pyjwt.ExpiredSignatureError:
            refresh_payload = None
        except pyjwt.InvalidTokenError:
            raise InvalidTokenError("Invalid refresh token.") from None

        refresh_jti: str = ""
        user_uuid: str = ""

        if refresh_payload is not None:
            if refresh_payload.get("type") != "refresh":
                raise InvalidTokenError("Token is not a refresh token.")
            refresh_jti = refresh_payload["jti"]
            user_uuid = refresh_payload["sub"]
            remaining = refresh_payload["exp"] - datetime.now(UTC).timestamp()
            ttl = max(int(remaining), 1)
            await self._cache.set(f"token:blacklist:{refresh_jti}", "1", ttl)

        # --- access token ---
        access_jti: str | None = None
        access_payload = None

        if command.access_token:
            try:
                access_payload = self._jwt.decode(command.access_token)
            except pyjwt.ExpiredSignatureError:
                access_payload = None
            except pyjwt.InvalidTokenError:
                raise InvalidTokenError("Invalid access token.") from None

        if access_payload is not None:
            if access_payload.get("type") != "access":
                raise InvalidTokenError("Token is not an access token.")
            access_jti = access_payload["jti"]
            if not user_uuid:
                user_uuid = access_payload["sub"]
            remaining = access_payload["exp"] - datetime.now(UTC).timestamp()
            ttl = max(int(remaining), 1)
            await self._cache.set(f"token:blacklist:{access_jti}", "1", ttl)

        if user_uuid:
            await self._event_bus.publish(
                UserLoggedOutEvent(user_uuid=user_uuid, jti=refresh_jti, access_jti=access_jti)
            )

        return LogoutResult()
