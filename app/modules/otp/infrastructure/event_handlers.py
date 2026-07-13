import logging
from collections.abc import Callable, Coroutine
from typing import Any

from app.core.cache import ICacheService
from app.core.database import AsyncSessionLocal
from app.core.email import send_otp_email
from app.core.event_bus import IEventBus
from app.modules.auth.domain.events import UserLoggedInEvent
from app.modules.otp.cqrs.command import GenerateOtpCommand
from app.modules.otp.domain.value_objects import OTP_EXPIRY_SECONDS, OtpType
from app.modules.otp.infrastructure.persistence.repository import SQLAlchemyOtpRepository
from app.modules.otp.use_cases.generate_otp import GenerateOtpUseCase

logger = logging.getLogger(__name__)


def create_generate_login_otp_handler(
    cache: ICacheService, event_bus: IEventBus
) -> Callable[[UserLoggedInEvent], Coroutine[Any, Any, None]]:
    """Return an event handler that generates a login OTP when a user logs in."""

    async def handler(event: UserLoggedInEvent) -> None:
        async with AsyncSessionLocal() as session:
            try:
                repo = SQLAlchemyOtpRepository(session)
                use_case = GenerateOtpUseCase(otp_repo=repo, cache=cache, event_bus=event_bus)
                command = GenerateOtpCommand(user_uuid=event.user_uuid, otp_type=OtpType.LOGIN)
                result = await use_case.execute(command)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        expiry_minutes = OTP_EXPIRY_SECONDS[OtpType.LOGIN] // 60
        try:
            await send_otp_email(to_email=event.email, code=result.code, expiry_minutes=expiry_minutes)
        except Exception:
            logger.exception("Failed to send OTP email to %s", event.email)

    return handler
