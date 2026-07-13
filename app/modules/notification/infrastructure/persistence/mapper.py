"""Map between notification domain entities and SQLAlchemy models."""

from app.modules.notification.domain.entities import Notification
from app.modules.notification.infrastructure.persistence.models import NotificationModel


def map_to_domain(model: NotificationModel) -> Notification:
    return Notification(
        id=model.id,
        event_type=model.event_type,
        aggregate_type=model.aggregate_type,
        aggregate_id=model.aggregate_id,
        message=model.message,
        created_at=model.created_at,
    )


def map_to_model(entity: Notification) -> NotificationModel:
    return NotificationModel(
        id=entity.id,
        event_type=entity.event_type,
        aggregate_type=entity.aggregate_type,
        aggregate_id=entity.aggregate_id,
        message=entity.message,
    )
