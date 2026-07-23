"""Shared fakes and factories for admin tests.

Hermetic: no database, no Redis. Mirrors the repo's existing test style
(in-memory doubles + dependency overrides).
"""

from typing import Any, cast

import pytest

from app.admin.auth import AdminAuthenticator
from app.core.cache import ICacheService
from app.core.hasher import get_password_hash
from app.modules.rbac.domain.entities import Permission
from app.modules.rbac.domain.interfaces import IRbacRepository
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.interfaces import IUserRepository
from app.modules.user.domain.value_objects import Email, HashedPassword, PhoneNumber

TEST_PASSWORD = "AdminPass123!"


class FakeUserRepository:
    """In-memory user double exposing only what the admin authenticator uses."""

    def __init__(self, users: list[User] | None = None) -> None:
        self._users = {u.email.value: u for u in users or []}

    async def get_by_email(self, email: Email) -> User | None:
        return self._users.get(email.value)

    async def get_by_uuid(self, uuid: str) -> User | None:
        for user in self._users.values():
            if user.uuid == uuid:
                return user
        return None


class FakeRbacRepository:
    """In-memory RBAC double keyed by user id."""

    def __init__(self, permissions_by_user: dict[int, list[str]] | None = None) -> None:
        self._permissions_by_user = permissions_by_user or {}

    async def get_user_permissions(self, user_id: int) -> list[Permission]:
        return [Permission(name=name) for name in self._permissions_by_user.get(user_id, [])]


class FakeCache:
    """Dict-backed cache honoring the ICacheService get/set contract."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def get(self, key: str) -> Any | None:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._store


def make_user(
    *,
    user_id: int = 1,
    uuid: str = "user-uuid-1",
    email: str = "admin@example.com",
    password: str = TEST_PASSWORD,
    status: UserStatus = UserStatus.ACTIVE,
    is_superuser: bool = False,
) -> User:
    return User(
        id=user_id,
        uuid=uuid,
        email=Email(email),
        hashed_password=HashedPassword(get_password_hash(password)),
        username=email.split("@")[0],
        phone_number=PhoneNumber("+1234567890"),
        status=status,
        is_superuser=is_superuser,
    )


def make_authenticator(
    users: list[User], permissions_by_user: dict[int, list[str]] | None = None, cache: FakeCache | None = None
) -> AdminAuthenticator:
    """Build an authenticator with in-memory doubles (typed via cast for mypy)."""
    return AdminAuthenticator(
        user_repo=cast(IUserRepository, FakeUserRepository(users)),
        rbac_repo=cast(IRbacRepository, FakeRbacRepository(permissions_by_user)),
        cache=cast(ICacheService, cache or FakeCache()),
    )


@pytest.fixture
def superuser() -> User:
    return make_user(is_superuser=True)
