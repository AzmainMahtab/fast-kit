"""Notification Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: int
    event_type: str
    aggregate_type: str
    aggregate_id: int | None
    message: str
    created_at: datetime | None

    @classmethod
    def from_domain(cls, notification) -> "NotificationResponse":
        return cls(
            id=notification.id,
            event_type=notification.event_type,
            aggregate_type=notification.aggregate_type,
            aggregate_id=notification.aggregate_id,
            message=notification.message,
            created_at=notification.created_at,
        )
