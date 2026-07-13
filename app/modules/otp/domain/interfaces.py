from abc import ABC, abstractmethod

from app.modules.otp.domain.entities import OneTimePassword
from app.modules.otp.domain.value_objects import OtpType


class IOtpRepository(ABC):
    @abstractmethod
    async def commit(self) -> None:
        """Persist all pending changes to the underlying store."""
        ...

    @abstractmethod
    async def create(self, otp: OneTimePassword) -> OneTimePassword:
        """Persist a new OTP entity."""
        ...

    @abstractmethod
    async def find_by_uuid(self, uuid: str) -> OneTimePassword | None:
        """Lookup an OTP by its UUID."""
        ...

    @abstractmethod
    async def find_valid_by_user_and_type(self, user_uuid: str, otp_type: OtpType) -> OneTimePassword | None:
        """Return the most recent *unused* and *non-expired* OTP for a given user and type."""
        ...

    @abstractmethod
    async def find_latest_by_user_and_type(self, user_uuid: str, otp_type: OtpType) -> OneTimePassword | None:
        """Return the most recent OTP for a user and type regardless of expiry or usage status."""
        ...

    @abstractmethod
    async def mark_as_used(self, otp_uuid: str) -> None:
        """Mark an OTP as consumed."""
        ...
