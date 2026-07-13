"""Notification repository ports."""

from abc import ABC, abstractmethod

from app.modules.notification.domain.entities import Notification


class INotificationRepository(ABC):
    """Port for notification persistence."""

    @abstractmethod
    async def create(self, notification: Notification) -> Notification: ...

    @abstractmethod
    async def list_recent(self, limit: int = 50) -> list[Notification]: ...

    @abstractmethod
    async def commit(self) -> None: ...
