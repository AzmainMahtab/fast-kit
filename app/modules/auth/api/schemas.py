from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.modules.user.domain.entities import User


class LoginRequest(BaseModel):
    """Request body for the ``/auth/login`` endpoint.

    Attributes:
        email: Registered email address. Validated as RFC 5321-compliant.
        password: The account's plain-text password.
    """

    email: EmailStr = Field(description="Registered email address.")
    password: str = Field(description="Account password.")


class RefreshRequest(BaseModel):
    """Request body for the ``/auth/refresh`` endpoint.

    Attributes:
        refresh_token: A valid, non-blacklisted refresh token.
    """

    refresh_token: str = Field(description="Valid refresh token issued at login.")


class LogoutRequest(BaseModel):
    """Request body for the ``/auth/logout`` endpoint.

    Attributes:
        refresh_token: The refresh token to revoke. It will be blacklisted
            for the remainder of its natural lifetime.
    """

    refresh_token: str = Field(description="Refresh token to invalidate.")


class TokenResponse(BaseModel):
    """Response body returned after a successful login or token refresh.

    Attributes:
        access_token: Short-lived JWT (default 15 min) for authenticating API requests.
        refresh_token: Long-lived JWT (default 7 days) for obtaining new access tokens.
        token_type: Always ``"bearer"``.
    """

    access_token: str = Field(description="Short-lived JWT access token.")
    refresh_token: str = Field(description="Long-lived JWT refresh token.")
    token_type: str = "bearer"


class UserProfileResponse(BaseModel):
    """Response body for the authenticated user's profile.

    Attributes:
        uuid: The user's UUID v7 identifier.
        email: The user's email address.
        username: The user's unique username.
        phone_number: The user's phone number with country code.
        first_name: Optional first name.
        last_name: Optional last name.
        status: Current account status.
        created_at: Timestamp of account creation.
        updated_at: Timestamp of last update.
        deleted_at: Timestamp of soft deletion, if applicable.
    """

    uuid: str = Field(description="Universally unique identifier (UUID v7).")
    email: str = Field(description="Email address of the user.")
    username: str = Field(description="Unique username.")
    phone_number: str = Field(description="Phone number with country code.")
    first_name: str | None = Field(default=None, description="Optional first name.")
    last_name: str | None = Field(default=None, description="Optional last name.")
    status: str = Field(description="Current account status.")
    is_superuser: bool = Field(default=False, description="Whether the user has superuser privileges.")
    created_at: str | None = Field(default=None, description="Timestamp of account creation.")
    updated_at: str | None = Field(default=None, description="Timestamp of last update.")
    deleted_at: str | None = Field(default=None, description="Timestamp of soft deletion, if applicable.")

    @classmethod
    def from_entity(cls, user: User) -> UserProfileResponse:
        """Build a response schema from a ``User`` domain entity.

        Args:
            user: The ``User`` domain entity.

        Returns:
            A ``UserProfileResponse`` with all fields populated.
        """
        return cls(
            uuid=user.uuid or "",
            email=user.email.value,
            username=user.username,
            phone_number=user.phone_number.value,
            first_name=user.first_name,
            last_name=user.last_name,
            status=user.status.value if hasattr(user.status, "value") else user.status,
            is_superuser=user.is_superuser,
            created_at=_format_dt(user.created_at),
            updated_at=_format_dt(user.updated_at),
            deleted_at=_format_dt(user.deleted_at),
        )


def _format_dt(dt: datetime | None) -> str | None:
    """Format a datetime to ISO string, or return None."""
    if dt is None:
        return None
    return dt.isoformat()


class ActivateAccountRequest(BaseModel):
    code: str = Field(min_length=4, max_length=8, pattern=r"^\d{4,8}$", description="The numeric OTP code.")


class ActivateAccountResponse(BaseModel):
    message: str


class SendActivationOtpResponse(BaseModel):
    message: str
