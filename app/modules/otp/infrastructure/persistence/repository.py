import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.otp.domain.entities import OneTimePassword
from app.modules.otp.domain.interfaces import IOtpRepository
from app.modules.otp.domain.value_objects import OtpType
from app.modules.otp.infrastructure.persistence.mapper import map_to_domain, map_to_persistence
from app.modules.otp.infrastructure.persistence.models import OtpModel


class SQLAlchemyOtpRepository(IOtpRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def create(self, otp: OneTimePassword) -> OneTimePassword:
        orm_model = map_to_persistence(otp)
        self.session.add(orm_model)
        await self.session.flush()
        await self.session.refresh(orm_model)
        return map_to_domain(orm_model)

    async def find_by_uuid(self, uuid: str) -> OneTimePassword | None:
        stmt = select(OtpModel).where(OtpModel.uuid == uuid)
        result = await self.session.execute(stmt)
        orm_model = result.scalar_one_or_none()
        return map_to_domain(orm_model) if orm_model else None

    async def find_valid_by_user_and_type(self, user_uuid: str, otp_type: OtpType) -> OneTimePassword | None:
        from datetime import datetime

        user_uuid_obj = uuid.UUID(user_uuid)
        stmt = (
            select(OtpModel)
            .where(
                OtpModel.user_uuid == user_uuid_obj,
                OtpModel.otp_type == otp_type.value,
                OtpModel.is_used.is_(False),
                OtpModel.expires_at > datetime.now(UTC),
            )
            .order_by(OtpModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        orm_model = result.scalar_one_or_none()
        return map_to_domain(orm_model) if orm_model else None

    async def find_latest_by_user_and_type(self, user_uuid: str, otp_type: OtpType) -> OneTimePassword | None:
        user_uuid_obj = uuid.UUID(user_uuid)
        stmt = (
            select(OtpModel)
            .where(OtpModel.user_uuid == user_uuid_obj, OtpModel.otp_type == otp_type.value)
            .order_by(OtpModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        orm_model = result.scalar_one_or_none()
        return map_to_domain(orm_model) if orm_model else None

    async def mark_as_used(self, otp_uuid: str) -> None:
        stmt = select(OtpModel).where(OtpModel.uuid == otp_uuid)
        result = await self.session.execute(stmt)
        orm_model = result.scalar_one_or_none()
        if orm_model:
            orm_model.is_used = True
            await self.session.flush()
