from dataclasses import dataclass


@dataclass(frozen=True)
class UserLoggedInEvent:
    """Domain Event: Fired when a user successfully logs in."""

    user_uuid: str
    email: str


@dataclass(frozen=True)
class UserRefreshedTokenEvent:
    """Domain Event: Fired when a user rotates their refresh token."""

    user_uuid: str
    old_jti: str
    new_jti: str


@dataclass(frozen=True)
class UserLoggedOutEvent:
    """Domain Event: Fired when a user explicitly revokes their tokens.

    The ``jti`` field holds the refresh token's JTI. ``access_jti`` is
    the access token's JTI if an access token was provided during logout,
    otherwise ``None``.
    """

    user_uuid: str
    jti: str
    access_jti: str | None = None
