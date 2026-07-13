from abc import ABC, abstractmethod

from app.core.pagination import PaginationParams
from app.modules.owner.domain.entities import Owner


class IOwnerRepository(ABC):
    @abstractmethod
    async def commit(self) -> None:
        """Persist all pending changes to the underlying store."""
        pass

    @abstractmethod
    async def get_by_id(self, owner_id: int) -> Owner | None:
        pass

    @abstractmethod
    async def get_by_uuid(self, uuid: str) -> Owner | None:
        pass

    @abstractmethod
    async def get_by_user_id(self, user_id: int) -> Owner | None:
        pass

    @abstractmethod
    async def create(self, owner: Owner) -> Owner:
        pass

    @abstractmethod
    async def list_all(self, pagination: PaginationParams = PaginationParams()) -> tuple[list[Owner], int]:
        pass
