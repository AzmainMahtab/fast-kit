from app.core.cache import ICacheService
from app.core.event_bus import IEventBus
from app.core.hasher import verify_password
from app.modules.otp.cqrs.command import ValidateOtpCommand
from app.modules.otp.cqrs.result import ValidateOtpResult
from app.modules.otp.domain.events import OtpValidatedEvent
from app.modules.otp.domain.exceptions import InvalidOtpError, OtpAlreadyUsedError, OtpExpiredError
from app.modules.otp.domain.interfaces import IOtpRepository

OTP_CACHE_PREFIX = "otp:"


class ValidateOtpUseCase:
    """Validate a user-provided OTP code.

    Fast-path: read the plain-text code from cache and compare directly.
    Fallback: load the latest OTP from DB, check expiry/usage, verify hash.
    """

    def __init__(self, otp_repo: IOtpRepository, cache: ICacheService, event_bus: IEventBus):
        self._otp_repo = otp_repo
        self._cache = cache
        self._event_bus = event_bus

    async def execute(self, command: ValidateOtpCommand) -> ValidateOtpResult:
        """Validate an OTP code for a given user and type.

        Args:
            command: The validate command with ``user_uuid``, ``otp_type``, and ``code``.

        Returns:
            A ``ValidateOtpResult`` indicating success.

        Raises:
            InvalidOtpError: The provided code does not match.
            OtpExpiredError: The OTP has expired.
            OtpAlreadyUsedError: The OTP has already been consumed.
        """
        # Fast path: check cache first
        cached = await self._cache.get(f"{OTP_CACHE_PREFIX}{command.user_uuid}:{command.otp_type.value}")
        if cached and cached.get("code") == command.code:
            otp_uuid = cached["uuid"]
            await self._cache.delete(f"{OTP_CACHE_PREFIX}{command.user_uuid}:{command.otp_type.value}")
            await self._otp_repo.mark_as_used(otp_uuid)
            await self._event_bus.publish(
                OtpValidatedEvent(user_uuid=command.user_uuid, otp_type=command.otp_type, otp_uuid=otp_uuid)
            )
            return ValidateOtpResult(success=True, otp_uuid=otp_uuid)

        # Fallback: lookup the latest OTP regardless of validity status
        otp = await self._otp_repo.find_latest_by_user_and_type(command.user_uuid, command.otp_type)

        if otp is None:
            raise InvalidOtpError("No valid OTP found for this user and type.")

        if otp.is_expired:
            raise OtpExpiredError("OTP has expired.")

        if otp.is_used:
            raise OtpAlreadyUsedError("OTP has already been used.")

        if not verify_password(command.code, otp.code_hash):
            raise InvalidOtpError("Invalid OTP code.")

        # Mark used and publish event
        if otp.uuid is None:
            raise RuntimeError("OTP entity must have a UUID.")
        await self._otp_repo.mark_as_used(otp.uuid)
        await self._cache.delete(f"{OTP_CACHE_PREFIX}{command.user_uuid}:{command.otp_type.value}")

        await self._event_bus.publish(
            OtpValidatedEvent(user_uuid=command.user_uuid, otp_type=command.otp_type, otp_uuid=otp.uuid)
        )

        return ValidateOtpResult(success=True, otp_uuid=otp.uuid)
