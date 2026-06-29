import secrets
from datetime import UTC, datetime, timedelta

from app.core.cache import ICacheService
from app.core.event_bus import IEventBus
from app.core.hasher import get_password_hash
from app.modules.otp.cqrs.command import GenerateOtpCommand
from app.modules.otp.cqrs.result import GenerateOtpResult
from app.modules.otp.domain.entities import OneTimePassword
from app.modules.otp.domain.events import OtpGeneratedEvent
from app.modules.otp.domain.interfaces import IOtpRepository
from app.modules.otp.domain.value_objects import OTP_EXPIRY_SECONDS, OTP_LENGTH

OTP_CACHE_PREFIX = "otp:"


class GenerateOtpUseCase:
    """Generate a new OTP for a user and store it securely.

    The plain-text code is cached in Redis for fast validation; the hash
    is persisted in the database as a fallback.
    """

    def __init__(self, otp_repo: IOtpRepository, cache: ICacheService, event_bus: IEventBus):
        self._otp_repo = otp_repo
        self._cache = cache
        self._event_bus = event_bus

    async def execute(self, command: GenerateOtpCommand) -> GenerateOtpResult:
        """Generate an OTP, persist it, and cache it.

        Args:
            command: The generate command with ``user_uuid`` and ``otp_type``.

        Returns:
            A ``GenerateOtpResult`` with the OTP UUID and expiry time.
        """
        otp_length = OTP_LENGTH[command.otp_type]
        ttl = OTP_EXPIRY_SECONDS[command.otp_type]

        code = self._generate_code(otp_length)
        code_hash = get_password_hash(code)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl)

        otp = OneTimePassword(
            user_uuid=command.user_uuid,
            otp_type=command.otp_type,
            code_hash=code_hash,
            expires_at=expires_at,
        )

        otp = await self._otp_repo.create(otp)
        if otp.uuid is None:
            raise RuntimeError("Repository must assign a UUID on create.")

        await self._cache.set(
            f"{OTP_CACHE_PREFIX}{command.user_uuid}:{command.otp_type.value}",
            {"code": code, "uuid": otp.uuid},
            ttl,
        )

        await self._event_bus.publish(
            OtpGeneratedEvent(user_uuid=command.user_uuid, otp_type=command.otp_type, otp_uuid=otp.uuid)
        )

        return GenerateOtpResult(otp_uuid=otp.uuid, expires_at=expires_at, code=code)

    @staticmethod
    def _generate_code(length: int) -> str:
        """Generate a cryptographically-secure numeric OTP code."""
        # secrets.randbelow(10**length) could produce a leading-zero issue;
        # instead generate each digit independently.
        return "".join(str(secrets.randbelow(10)) for _ in range(length))
