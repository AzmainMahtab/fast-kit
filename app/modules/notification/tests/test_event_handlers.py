import pytest

from app.core.event_bus import InMemoryEventBus
from app.modules.notification.domain.entities import Notification
from app.modules.notification.domain.interfaces import INotificationRepository
from app.modules.notification.infrastructure.event_handlers import (
    create_job_status_changed_handler,
)
from app.modules.ordering.domain.events import JobStatusChanged


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


@pytest.mark.asyncio
async def test_job_status_changed_handler_records_notification():
    repo = InMemoryNotificationRepository()
    bus = InMemoryEventBus()

    async def get_repository():
        return repo

    handler = create_job_status_changed_handler(get_repository)
    bus.subscribe(JobStatusChanged, handler)

    await bus.publish(
        JobStatusChanged(
            job_id=1,
            job_uuid="JOB-001",
            old_status="PENDING",
            new_status="RECEIVED_ARTWORK",
            user_id=1,
            reason="Artwork received",
        )
    )

    assert len(repo._notifications) == 1
    assert repo._notifications[0].event_type == "ordering.job_status_changed"
