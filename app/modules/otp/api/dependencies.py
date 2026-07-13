from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import ICacheService, get_security_cache_service
from app.core.database import get_db
from app.core.event_bus import IEventBus
from app.modules.otp.domain.interfaces import IOtpRepository
from app.modules.otp.infrastructure.persistence.repository import SQLAlchemyOtpRepository
from app.modules.otp.use_cases.generate_otp import GenerateOtpUseCase
from app.modules.otp.use_cases.validate_otp import ValidateOtpUseCase


async def get_otp_repo(db: AsyncSession = Depends(get_db)) -> IOtpRepository:
    return SQLAlchemyOtpRepository(db)


def get_event_bus(request: Request) -> IEventBus:
    return cast(IEventBus, request.app.state.event_bus)


async def get_generate_otp_use_case(
    repo: IOtpRepository = Depends(get_otp_repo),
    cache: ICacheService = Depends(get_security_cache_service),
    event_bus: IEventBus = Depends(get_event_bus),
) -> GenerateOtpUseCase:
    return GenerateOtpUseCase(otp_repo=repo, cache=cache, event_bus=event_bus)


async def get_validate_otp_use_case(
    repo: IOtpRepository = Depends(get_otp_repo),
    cache: ICacheService = Depends(get_security_cache_service),
    event_bus: IEventBus = Depends(get_event_bus),
) -> ValidateOtpUseCase:
    return ValidateOtpUseCase(otp_repo=repo, cache=cache, event_bus=event_bus)
