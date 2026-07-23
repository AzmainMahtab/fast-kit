"""Creation logic for admin-created users, kept pure for testability.

The ModelView hooks in ``app.admin.views`` are thin adapters over these
functions. Everything here is DB-agnostic: uniqueness is checked through
an injected ``exists`` callback, so unit tests need no database.

Validation deliberately reuses the domain value objects (``Email``,
``PhoneNumber``, ``PlainPassword``) so password-strength and format rules
live in exactly one place — the domain layer.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from app.core.hasher import get_password_hash
from app.modules.user.domain.entities import UserStatus
from app.modules.user.domain.value_objects import Email, PhoneNumber, PlainPassword

# Fields with unique constraints on the users table.
UNIQUE_USER_FIELDS = ("email", "username", "phone_number")

# Injected lookup: (field_name, value) -> whether a user already has it.
FieldExists = Callable[[str, Any], Awaitable[bool]]


class AdminUserCreationError(ValueError):
    """User-facing creation failure (rendered as an alert in the admin)."""


def _validate_value_object(vo_type: type, raw: str, field_label: str) -> None:
    try:
        vo_type(raw)
    except ValueError as exc:
        raise AdminUserCreationError(f"Invalid {field_label}: {exc}") from exc


def prepare_new_user_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate create-form data and derive secure defaults.

    - Requires the plain ``password`` field, validates it with the domain
      ``PlainPassword`` rules, and replaces it with an Argon2 hash under
      ``hashed_password``. The plain password never leaves this function.
    - Validates email/phone formats via the domain value objects.
    - Defaults ``status`` to ``active`` when the form left it blank, and
      rejects unknown status values.

    Args:
        data: The validated WTForms ``form.data`` dict.

    Returns:
        A new dict safe to persist as a ``UserModel``.

    Raises:
        AdminUserCreationError: With a user-facing message on any failure.
    """
    prepared = dict(data)

    password = prepared.pop("password", None)
    if not password or not str(password).strip():
        raise AdminUserCreationError("Password is required for a new user.")
    _validate_value_object(PlainPassword, str(password), "password")
    prepared["hashed_password"] = get_password_hash(str(password))

    _validate_value_object(Email, str(prepared.get("email") or ""), "email")
    _validate_value_object(PhoneNumber, str(prepared.get("phone_number") or ""), "phone number")

    status = prepared.get("status")
    if not status:
        prepared["status"] = UserStatus.ACTIVE.value
    elif status not in {s.value for s in UserStatus}:
        valid = ", ".join(sorted(s.value for s in UserStatus))
        raise AdminUserCreationError(f"Invalid status '{status}'. Valid values: {valid}.")

    return prepared


async def ensure_unique_user_fields(data: Mapping[str, Any], exists: FieldExists) -> None:
    """Reject duplicates for unique user fields before insert.

    Args:
        data: The prepared user data.
        exists: Injected async lookup returning True when a user already
            holds the given field value.

    Raises:
        AdminUserCreationError: Naming the first duplicated field.
    """
    for field in UNIQUE_USER_FIELDS:
        value = data.get(field)
        if value is None:
            continue
        if await exists(field, value):
            label = field.replace("_", " ")
            raise AdminUserCreationError(f"A user with this {label} already exists.")
