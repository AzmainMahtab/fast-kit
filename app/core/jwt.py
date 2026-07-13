from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt

from app.core.settings import settings


class JWTService:
    """Symmetric JWT token creation and verification using PyJWT (HS256).

    Configurable via environment variables read from ``settings`` at runtime.
    Produces two distinct token types:

    - **Access token**: short-lived (default 15 minutes), used to authenticate API requests.
    - **Refresh token**: long-lived (default 7 days), used to obtain new access tokens.
    """

    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str | None = None,
        access_expire_minutes: int | None = None,
        refresh_expire_days: int | None = None,
    ) -> None:
        self._secret_key = secret_key or settings.JWT_SECRET_KEY
        self._algorithm = algorithm or settings.ALGORITHM
        self._access_expire_minutes = access_expire_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self._refresh_expire_days = refresh_expire_days or settings.REFRESH_TOKEN_EXPIRE_DAYS

    def create_access_token(self, user_uuid: str) -> str:
        """Create a short-lived access token for the given user.

        Args:
            user_uuid: The user's UUID v7 identifier.

        Returns:
            A signed JWT string with ``type: "access"``, valid for
            ``ACCESS_TOKEN_EXPIRE_MINUTES``.
        """
        now = datetime.now(UTC)
        payload = {
            "sub": user_uuid,
            "type": "access",
            "jti": str(uuid4()),
            "iat": now,
            "exp": now + timedelta(minutes=self._access_expire_minutes),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def create_refresh_token(self, user_uuid: str) -> str:
        """Create a long-lived refresh token for the given user.

        Args:
            user_uuid: The user's UUID v7 identifier.

        Returns:
            A signed JWT string with ``type: "refresh"``, valid for
            ``REFRESH_TOKEN_EXPIRE_DAYS``.
        """
        now = datetime.now(UTC)
        payload = {
            "sub": user_uuid,
            "type": "refresh",
            "jti": str(uuid4()),
            "iat": now,
            "exp": now + timedelta(days=self._refresh_expire_days),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def decode(self, token: str) -> dict[str, Any]:
        """Decode and verify a JWT token.

        Args:
            token: The signed JWT string.

        Returns:
            The decoded payload dict.

        Raises:
            jwt.ExpiredSignatureError: Token has expired.
            jwt.InvalidTokenError: Token is malformed or signature is invalid.
        """
        return jwt.decode(token, self._secret_key, algorithms=[self._algorithm])

    def create_token_pair(self, user_uuid: str) -> dict[str, str]:
        """Convenience method to create both tokens in a single call.

        Args:
            user_uuid: The user's UUID v7 identifier.

        Returns:
            Dict with ``access_token`` and ``refresh_token`` keys.
        """
        return {
            "access_token": self.create_access_token(user_uuid),
            "refresh_token": self.create_refresh_token(user_uuid),
        }
