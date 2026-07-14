"""Notification API dependency providers."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.notification.domain.interfaces import INotificationRepository
from app.modules.notification.infrastructure.persistence.repository import (
    SQLAlchemyNotificationRepository,
)
from app.modules.notification.use_cases.list_notifications import ListNotificationsUseCase


async def get_notification_repo(db: AsyncSession = Depends(get_db)) -> INotificationRepository:
    return SQLAlchemyNotificationRepository(db)


async def get_list_notifications_use_case(
    notification_repo: INotificationRepository = Depends(get_notification_repo),
) -> ListNotificationsUseCase:
    return ListNotificationsUseCase(notification_repo=notification_repo)
