import pytest

from app.modules.notification.domain.entities import Notification
from app.modules.notification.domain.interfaces import INotificationRepository


class InMemoryNotificationRepository(INotificationRepository):
    def __init__(self):
        self._notifications: list[Notification] = []

    async def commit(self) -> None:
        return

    async def create(self, notification: Notification) -> Notification:
        notification.id = len(self._notifications) + 1
        self._notifications.append(notification)
        return notification

    async def list_recent(self, limit: int = 50) -> list[Notification]:
        return self._notifications[:limit]


@pytest.fixture
def notification_repo():
    return InMemoryNotificationRepository()
