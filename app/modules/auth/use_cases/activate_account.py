from app.core.cache import ICacheService
from app.core.event_bus import IEventBus
from app.modules.auth.cqrs.command import ActivateAccountCommand
from app.modules.auth.cqrs.result import ActivateAccountResult
from app.modules.auth.domain.exception import AccountAlreadyActiveError, UserNotFoundError
from app.modules.otp.cqrs.command import ValidateOtpCommand
from app.modules.otp.domain.interfaces import IOtpRepository
from app.modules.otp.domain.value_objects import OtpType
from app.modules.otp.use_cases.validate_otp import ValidateOtpUseCase
from app.modules.user.domain.entities import UserStatus
from app.modules.user.domain.events import UserUpdatedEvent
from app.modules.user.domain.interfaces import IUserRepository


class ActivateAccountUseCase:
    def __init__(
        self, user_repo: IUserRepository, otp_repo: IOtpRepository, cache: ICacheService, event_bus: IEventBus
    ):
        self._user_repo = user_repo
        self._otp_repo = otp_repo
        self._cache = cache
        self._event_bus = event_bus

    async def execute(self, command: ActivateAccountCommand) -> ActivateAccountResult:
        user = await self._user_repo.get_by_uuid(command.user_uuid)
        if user is None:
            raise UserNotFoundError("User not found.")

        if user.status != UserStatus.PENDING_VERIFICATION:
            raise AccountAlreadyActiveError("Account is already active.")

        validate = ValidateOtpUseCase(otp_repo=self._otp_repo, cache=self._cache, event_bus=self._event_bus)
        await validate.execute(
            ValidateOtpCommand(user_uuid=command.user_uuid, otp_type=OtpType.EMAIL_VERIFY, code=command.code)
        )

        user.verify()
        await self._user_repo.update(user)
        await self._user_repo.commit()

        await self._event_bus.publish(UserUpdatedEvent(user_uuid=str(user.uuid), email=user.email.value))

        return ActivateAccountResult()
