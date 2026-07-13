"""Notification SQLAlchemy repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notification.domain.entities import Notification
from app.modules.notification.domain.interfaces import INotificationRepository
from app.modules.notification.infrastructure.persistence.mapper import (
    map_to_domain,
    map_to_model,
)
from app.modules.notification.infrastructure.persistence.models import NotificationModel


class SQLAlchemyNotificationRepository(INotificationRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def create(self, notification: Notification) -> Notification:
        model = map_to_model(notification)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return map_to_domain(model)

    async def list_recent(self, limit: int = 50) -> list[Notification]:
        result = await self.session.execute(
            select(NotificationModel).order_by(NotificationModel.created_at.desc()).limit(limit)
        )
        models = result.scalars().all()
        return [map_to_domain(m) for m in models]
