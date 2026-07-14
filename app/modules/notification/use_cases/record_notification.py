"""Record notification use case."""

from app.modules.notification.domain.entities import Notification
from app.modules.notification.domain.interfaces import INotificationRepository


class RecordNotificationUseCase:
    """Persist a notification triggered by a domain event."""

    def __init__(self, notification_repo: INotificationRepository):
        self.notification_repo = notification_repo

    async def execute(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: int,
        message: str,
    ) -> Notification:
        notification = Notification(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            message=message,
        )
        saved = await self.notification_repo.create(notification)
        await self.notification_repo.commit()
        return saved
