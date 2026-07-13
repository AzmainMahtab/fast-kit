from abc import ABC, abstractmethod

from app.core.pagination import PaginationParams
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.value_objects import Email


class IUserRepository(ABC):
    @abstractmethod
    async def commit(self) -> None:
        """Persist all pending changes to the underlying store."""
        pass

    @abstractmethod
    async def get_by_email(self, email: Email) -> User | None:
        pass

    @abstractmethod
    async def get_by_id(self, user_id: int) -> User | None:
        pass

    @abstractmethod
    async def get_by_uuid(self, uuid: str) -> User | None:
        pass

    @abstractmethod
    async def get_by_username(self, username: str) -> User | None:
        pass

    @abstractmethod
    async def create(self, user: User) -> User:
        pass

    @abstractmethod
    async def update(self, user: User) -> User:
        pass

    @abstractmethod
    async def delete(self, uuid: str) -> None:
        pass

    @abstractmethod
    async def list_all(
        self,
        status: UserStatus | None = None,
        include_deleted: bool = False,
        pagination: PaginationParams = PaginationParams(),
    ) -> tuple[list[User], int]:
        pass
