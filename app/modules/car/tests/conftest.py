import pytest
import uuid_utils

from app.core.pagination import PaginationParams
from app.modules.car.domain.entities import Car
from app.modules.car.domain.interfaces import ICarRepository


class InMemoryCarRepository(ICarRepository):
    def __init__(self) -> None:
        self._cars: dict[int, Car] = {}
        self._next_id = 1

    async def commit(self) -> None:
        """No-op for the in-memory test double."""
        return

    def _find_by(self, predicate) -> Car | None:
        for car in self._cars.values():
            if predicate(car):
                return car
        return None

    async def get_by_id(self, car_id: int) -> Car | None:
        return self._cars.get(car_id)

    async def get_by_uuid(self, uuid: str) -> Car | None:
        return self._find_by(lambda c: c.uuid == uuid)

    async def create(self, car: Car) -> Car:
        car.id = self._next_id
        self._next_id += 1
        assert car.id is not None
        car.uuid = str(uuid_utils.uuid7())
        self._cars[car.id] = car
        return car

    async def list_by_owner(
        self, owner_id: int, pagination: PaginationParams = PaginationParams()
    ) -> tuple[list[Car], int]:
        filtered = [c for c in self._cars.values() if c.owner_id == owner_id]
        total = len(filtered)
        return filtered[pagination.offset : pagination.offset + pagination.limit], total

    async def list_all(self, pagination: PaginationParams = PaginationParams()) -> tuple[list[Car], int]:
        filtered = list(self._cars.values())
        total = len(filtered)
        return filtered[pagination.offset : pagination.offset + pagination.limit], total


@pytest.fixture
def car_repo() -> InMemoryCarRepository:
    return InMemoryCarRepository()
