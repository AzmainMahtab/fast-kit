"""Notification event handlers."""

from collections.abc import Awaitable, Callable, Coroutine
from typing import TypeVar

from app.core.event_bus import IEventBus
from app.modules.notification.domain.interfaces import INotificationRepository
from app.modules.notification.infrastructure.persistence.repository import (
    SQLAlchemyNotificationRepository,
)
from app.modules.notification.use_cases.record_notification import RecordNotificationUseCase

T = TypeVar("T")
GetRepository = Callable[[], Awaitable[INotificationRepository]]


def create_job_status_changed_handler(
    get_repository: GetRepository,
) -> Callable[..., Coroutine]:
    """Factory for the JobStatusChanged handler.

    The handler receives an async callable that returns a repository so each
    event is handled in its own transactional boundary.
    """

    async def handler(event) -> None:
        message = (
            f"Job {event.job_uuid} moved from {event.old_status} "
            f"to {event.new_status}"
        )
        repo = await get_repository()
        use_case = RecordNotificationUseCase(repo)
        await use_case.execute(
            event_type="ordering.job_status_changed",
            aggregate_type="job",
            aggregate_id=event.job_id,
            message=message,
        )

    return handler


def subscribe_notification_handlers(
    event_bus: IEventBus,
    get_repository: GetRepository,
) -> None:
    """Subscribe notification handlers to domain events at startup."""
    from app.modules.ordering.domain.events import JobStatusChanged

    event_bus.subscribe(
        JobStatusChanged,
        create_job_status_changed_handler(get_repository),
    )


def create_session_repository_factory(
    session_factory,
) -> GetRepository:
    """Wrap an async SQLAlchemy session factory into a repository provider."""

    async def get_repository() -> INotificationRepository:
        async with session_factory() as session:
            return SQLAlchemyNotificationRepository(session)

    return get_repository
