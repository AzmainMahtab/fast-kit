"""Unit tests for the admin user-creation logic — fully hermetic, no DB."""

import pytest

from app.admin.user_creation import AdminUserCreationError, ensure_unique_user_fields, prepare_new_user_data
from app.core.hasher import verify_password
from app.modules.user.domain.entities import UserStatus

VALID_PAYLOAD = {
    "email": "newuser@example.com",
    "username": "newuser",
    "phone_number": "+1555123456",
    "first_name": "New",
    "last_name": "User",
    "status": "",
    "is_superuser": False,
    "password": "StrongPass1!",
}


class TestPrepareNewUserData:
    def test_valid_payload_hashes_password_and_removes_plaintext(self) -> None:
        result = prepare_new_user_data(VALID_PAYLOAD)

        assert "password" not in result
        assert result["hashed_password"] != "StrongPass1!"
        assert verify_password("StrongPass1!", result["hashed_password"])

    def test_plain_password_never_appears_in_result(self) -> None:
        result = prepare_new_user_data(VALID_PAYLOAD)

        assert "StrongPass1!" not in (str(v) for v in result.values())

    def test_blank_status_defaults_to_active(self) -> None:
        result = prepare_new_user_data(VALID_PAYLOAD)

        assert result["status"] == UserStatus.ACTIVE.value

    def test_explicit_status_is_preserved(self) -> None:
        result = prepare_new_user_data({**VALID_PAYLOAD, "status": "suspended"})

        assert result["status"] == "suspended"

    def test_missing_password_is_rejected(self) -> None:
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "password"}

        with pytest.raises(AdminUserCreationError, match="Password is required"):
            prepare_new_user_data(payload)

    def test_blank_password_is_rejected(self) -> None:
        with pytest.raises(AdminUserCreationError, match="Password is required"):
            prepare_new_user_data({**VALID_PAYLOAD, "password": "   "})

    @pytest.mark.parametrize(
        "weak_password",
        [
            "Sh0rt!",  # too short
            "nouppercase1!",  # no uppercase letter
            "NoSpecialChar1",  # no special character
        ],
    )
    def test_weak_passwords_are_rejected_with_domain_rules(self, weak_password: str) -> None:
        with pytest.raises(AdminUserCreationError, match="Invalid password"):
            prepare_new_user_data({**VALID_PAYLOAD, "password": weak_password})

    def test_invalid_email_is_rejected(self) -> None:
        with pytest.raises(AdminUserCreationError, match="Invalid email"):
            prepare_new_user_data({**VALID_PAYLOAD, "email": "not-an-email"})

    def test_invalid_phone_number_is_rejected(self) -> None:
        with pytest.raises(AdminUserCreationError, match="Invalid phone number"):
            prepare_new_user_data({**VALID_PAYLOAD, "phone_number": "0123456789"})

    def test_invalid_status_is_rejected_with_valid_values_listed(self) -> None:
        with pytest.raises(AdminUserCreationError, match="Invalid status"):
            prepare_new_user_data({**VALID_PAYLOAD, "status": "bogus"})


class TestEnsureUniqueUserFields:
    async def test_all_unique_passes_and_checks_every_field(self) -> None:
        checked: list[str] = []

        async def exists(field: str, value: object) -> bool:
            checked.append(field)
            return False

        await ensure_unique_user_fields(VALID_PAYLOAD, exists)

        assert checked == ["email", "username", "phone_number"]

    async def test_duplicate_email_is_named_in_error(self) -> None:
        async def exists(field: str, value: object) -> bool:
            return field == "email"

        with pytest.raises(AdminUserCreationError, match="email already exists"):
            await ensure_unique_user_fields(VALID_PAYLOAD, exists)

    async def test_duplicate_phone_number_is_named_in_error(self) -> None:
        async def exists(field: str, value: object) -> bool:
            return field == "phone_number"

        with pytest.raises(AdminUserCreationError, match="phone number already exists"):
            await ensure_unique_user_fields(VALID_PAYLOAD, exists)

    async def test_missing_values_are_skipped(self) -> None:
        checked: list[str] = []

        async def exists(field: str, value: object) -> bool:
            checked.append(field)
            return False

        await ensure_unique_user_fields({"email": "a@b.com"}, exists)

        assert checked == ["email"]
