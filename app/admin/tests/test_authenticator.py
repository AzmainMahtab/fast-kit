"""Unit tests for AdminAuthenticator — the DB-agnostic verification core."""

import pytest

from app.admin.permissions import ADMIN_ACCESS_PERMISSION
from app.admin.tests.conftest import TEST_PASSWORD, FakeCache, make_authenticator, make_user
from app.modules.user.domain.entities import UserStatus


class TestVerifyLogin:
    async def test_superuser_with_valid_password_succeeds(self) -> None:
        user = make_user(is_superuser=True)
        auth = make_authenticator([user])

        result = await auth.verify_login(user.email.value, TEST_PASSWORD)

        assert result is user

    async def test_non_superuser_with_admin_access_permission_succeeds(self) -> None:
        user = make_user(user_id=7, is_superuser=False)
        auth = make_authenticator([user], permissions_by_user={7: [ADMIN_ACCESS_PERMISSION, "car:read"]})

        result = await auth.verify_login(user.email.value, TEST_PASSWORD)

        assert result is user

    async def test_non_superuser_without_permission_is_denied(self) -> None:
        user = make_user(user_id=7, is_superuser=False)
        auth = make_authenticator([user], permissions_by_user={7: ["car:read"]})

        assert await auth.verify_login(user.email.value, TEST_PASSWORD) is None

    async def test_wrong_password_is_denied(self) -> None:
        user = make_user(is_superuser=True)
        auth = make_authenticator([user])

        assert await auth.verify_login(user.email.value, "wrong-password") is None

    async def test_unknown_email_is_denied(self) -> None:
        auth = make_authenticator([])

        assert await auth.verify_login("nobody@example.com", TEST_PASSWORD) is None

    async def test_malformed_email_is_denied(self) -> None:
        auth = make_authenticator([])

        assert await auth.verify_login("not-an-email", TEST_PASSWORD) is None

    @pytest.mark.parametrize("status", [UserStatus.SUSPENDED, UserStatus.INACTIVE, UserStatus.PENDING_VERIFICATION])
    async def test_non_active_status_is_denied(self, status: UserStatus) -> None:
        user = make_user(is_superuser=True, status=status)
        auth = make_authenticator([user])

        assert await auth.verify_login(user.email.value, TEST_PASSWORD) is None

    async def test_permissions_are_cached_after_first_lookup(self) -> None:
        user = make_user(user_id=7, is_superuser=False)
        cache = FakeCache()
        auth = make_authenticator([user], permissions_by_user={7: [ADMIN_ACCESS_PERMISSION]}, cache=cache)

        assert await auth.verify_login(user.email.value, TEST_PASSWORD) is user
        assert cache._store[f"user_permissions:{user.id}"] == [ADMIN_ACCESS_PERMISSION]


class TestVerifySession:
    async def test_valid_active_superuser_session_succeeds(self) -> None:
        user = make_user(is_superuser=True)
        auth = make_authenticator([user])

        assert await auth.verify_session(str(user.uuid)) is user

    async def test_unknown_uuid_is_denied(self) -> None:
        auth = make_authenticator([make_user(is_superuser=True)])

        assert await auth.verify_session("no-such-uuid") is None

    async def test_suspended_user_session_is_denied(self) -> None:
        user = make_user(is_superuser=True, status=UserStatus.SUSPENDED)
        auth = make_authenticator([user])

        assert await auth.verify_session(str(user.uuid)) is None

    async def test_revoked_permission_invalidates_session(self) -> None:
        """A user who had admin access loses it immediately after revocation."""
        user = make_user(user_id=7, is_superuser=False)
        auth = make_authenticator([user], permissions_by_user={7: []})

        assert await auth.verify_session(str(user.uuid)) is None

    async def test_cached_permission_revocation_takes_effect(self) -> None:
        """Cached permission snapshots are honored (5-min TTL, same as the API)."""
        user = make_user(user_id=7, is_superuser=False)
        cache = FakeCache()
        cache._store[f"user_permissions:{user.id}"] = ["car:read"]
        auth = make_authenticator([user], permissions_by_user={7: [ADMIN_ACCESS_PERMISSION]}, cache=cache)

        # Cache says no admin:access, so denied even though DB would allow.
        assert await auth.verify_session(str(user.uuid)) is None
