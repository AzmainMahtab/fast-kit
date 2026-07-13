import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.pagination import PaginatedResponse
from app.modules.user.domain.entities import User, UserStatus


class UpdatableStatus(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class RegisterRequest(BaseModel):
    email: EmailStr = Field(description="Email address of the user. Must be a valid email format.")
    password: str = Field(description="Plain-text password. Will be hashed with Argon2id before storage.")
    password2: str = Field(description="Confirmation password. Must match password.")
    username: str = Field(description="Unique username for the user.")
    phone_number: str = Field(description="Phone number with country code (e.g. +1234567890). Must be unique.")
    first_name: str | None = Field(default=None, description="Optional first name.")
    last_name: str | None = Field(default=None, description="Optional last name.")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[^a-zA-Z0-9]", v):
            raise ValueError("Password must contain at least one special character.")
        return v

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        if not re.match(r"^\+[1-9]\d{1,14}$", v):
            raise ValueError("Invalid phone number format. Must be in E.164 format (e.g. +1234567890).")
        return v


class UpdateUserStatusRequest(BaseModel):
    status: UpdatableStatus = Field(description="New status value.")


class UserResponse(BaseModel):
    """Response body for a single user resource.

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

    model_config = ConfigDict(from_attributes=True)

    uuid: str = Field(description="Universally unique identifier (UUID v7).")
    email: str = Field(description="Email address of the user.")
    username: str = Field(description="Unique username.")
    phone_number: str = Field(description="Phone number with country code.")
    first_name: str | None = Field(default=None, description="Optional first name.")
    last_name: str | None = Field(default=None, description="Optional last name.")
    status: UserStatus = Field(description="Current account status.")
    is_superuser: bool = Field(default=False, description="Whether the user has superuser privileges.")
    created_at: datetime | None = Field(default=None, description="Timestamp of account creation.")
    updated_at: datetime | None = Field(default=None, description="Timestamp of last update.")
    deleted_at: datetime | None = Field(default=None, description="Timestamp of soft deletion, if applicable.")

    @classmethod
    def from_entity(cls, user: User) -> UserResponse:
        """Build a response schema from a ``User`` domain entity.

        Args:
            user: The ``User`` domain entity.

        Returns:
            A ``UserResponse`` with all fields populated.
        """
        return cls(
            uuid=user.uuid or "",
            email=user.email.value,
            username=user.username,
            phone_number=user.phone_number.value,
            first_name=user.first_name,
            last_name=user.last_name,
            status=user.status,
            is_superuser=user.is_superuser,
            created_at=user.created_at,
            updated_at=user.updated_at,
            deleted_at=user.deleted_at,
        )


UserListResponse = PaginatedResponse[UserResponse]
