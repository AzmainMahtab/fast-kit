from abc import ABC, abstractmethod

from app.core.pagination import PaginationParams
from app.modules.car.domain.entities import Car


class ICarRepository(ABC):
    @abstractmethod
    async def commit(self) -> None:
        """Persist all pending changes to the underlying store."""
        pass

    @abstractmethod
    async def get_by_id(self, car_id: int) -> Car | None:
        pass

    @abstractmethod
    async def get_by_uuid(self, uuid: str) -> Car | None:
        pass

    @abstractmethod
    async def create(self, car: Car) -> Car:
        pass

    @abstractmethod
    async def list_by_owner(
        self, owner_id: int, pagination: PaginationParams = PaginationParams()
    ) -> tuple[list[Car], int]:
        pass

    @abstractmethod
    async def list_all(self, pagination: PaginationParams = PaginationParams()) -> tuple[list[Car], int]:
        pass
