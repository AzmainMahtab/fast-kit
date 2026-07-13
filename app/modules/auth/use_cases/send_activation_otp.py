import logging

from app.core.cache import ICacheService
from app.core.email import send_otp_email
from app.core.event_bus import IEventBus
from app.modules.auth.cqrs.command import SendActivationOtpCommand
from app.modules.auth.cqrs.result import SendActivationOtpResult
from app.modules.auth.domain.exception import AccountAlreadyActiveError, UserNotFoundError
from app.modules.otp.cqrs.command import GenerateOtpCommand
from app.modules.otp.domain.interfaces import IOtpRepository
from app.modules.otp.domain.value_objects import OTP_EXPIRY_SECONDS, OtpType
from app.modules.otp.use_cases.generate_otp import GenerateOtpUseCase
from app.modules.user.domain.entities import UserStatus
from app.modules.user.domain.interfaces import IUserRepository

logger = logging.getLogger(__name__)


class SendActivationOtpUseCase:
    def __init__(
        self, user_repo: IUserRepository, otp_repo: IOtpRepository, cache: ICacheService, event_bus: IEventBus
    ):
        self._user_repo = user_repo
        self._otp_repo = otp_repo
        self._cache = cache
        self._event_bus = event_bus

    async def execute(self, command: SendActivationOtpCommand) -> SendActivationOtpResult:
        user = await self._user_repo.get_by_uuid(command.user_uuid)
        if user is None:
            raise UserNotFoundError("User not found.")

        if user.status != UserStatus.PENDING_VERIFICATION:
            raise AccountAlreadyActiveError("Account is already active.")

        generate = GenerateOtpUseCase(otp_repo=self._otp_repo, cache=self._cache, event_bus=self._event_bus)
        result = await generate.execute(GenerateOtpCommand(user_uuid=command.user_uuid, otp_type=OtpType.EMAIL_VERIFY))

        expiry_minutes = OTP_EXPIRY_SECONDS[OtpType.EMAIL_VERIFY] // 60
        try:
            await send_otp_email(to_email=user.email.value, code=result.code, expiry_minutes=expiry_minutes)
        except Exception:
            logger.exception("Failed to send activation OTP email to %s", user.email.value)

        return SendActivationOtpResult()
