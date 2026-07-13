import pytest
import pytest_asyncio

from app.core.cache import NullCache
from app.core.event_bus import InMemoryEventBus
from app.modules.otp.domain.entities import OneTimePassword
from app.modules.otp.domain.interfaces import IOtpRepository
from app.modules.otp.domain.value_objects import OtpType


class InMemoryOtpRepository(IOtpRepository):
    """Minimal in-memory OTP repository for unit tests."""

    def __init__(self) -> None:
        self._otps: dict[str, OneTimePassword] = {}

    async def commit(self) -> None:
        """No-op for the in-memory test double."""
        return

    async def create(self, otp: OneTimePassword) -> OneTimePassword:
        from uuid import uuid4

        otp.uuid = str(uuid4())
        self._otps[otp.uuid] = otp
        return otp

    async def find_by_uuid(self, uuid: str) -> OneTimePassword | None:
        return self._otps.get(uuid)

    async def find_valid_by_user_and_type(self, user_uuid: str, otp_type: OtpType) -> OneTimePassword | None:
        for otp in self._otps.values():
            if otp.user_uuid == user_uuid and otp.otp_type == otp_type and not otp.is_used and not otp.is_expired:
                return otp
        return None

    async def find_latest_by_user_and_type(self, user_uuid: str, otp_type: OtpType) -> OneTimePassword | None:
        for otp in self._otps.values():
            if otp.user_uuid == user_uuid and otp.otp_type == otp_type:
                return otp
        return None

    async def mark_as_used(self, otp_uuid: str) -> None:
        otp = self._otps.get(otp_uuid)
        if otp:
            otp.is_used = True


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def cache() -> NullCache:
    return NullCache()


@pytest_asyncio.fixture
async def otp_repo() -> InMemoryOtpRepository:
    return InMemoryOtpRepository()
