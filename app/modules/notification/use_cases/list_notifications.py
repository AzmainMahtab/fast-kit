"""List notifications use case."""

from app.modules.notification.domain.entities import Notification
from app.modules.notification.domain.interfaces import INotificationRepository


class ListNotificationsUseCase:
    """Read recent notifications."""

    def __init__(self, notification_repo: INotificationRepository):
        self.notification_repo = notification_repo

    async def execute(self, limit: int = 50) -> list[Notification]:
        return await self.notification_repo.list_recent(limit)
