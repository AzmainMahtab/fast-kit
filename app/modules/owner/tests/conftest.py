import pytest
import uuid_utils

from app.core.pagination import PaginationParams
from app.modules.owner.domain.entities import Owner
from app.modules.owner.domain.interfaces import IOwnerRepository


class InMemoryOwnerRepository(IOwnerRepository):
    def __init__(self) -> None:
        self._owners: dict[int, Owner] = {}
        self._next_id = 1

    async def commit(self) -> None:
        """No-op for the in-memory test double."""
        return

    def _find_by(self, predicate) -> Owner | None:
        for owner in self._owners.values():
            if predicate(owner):
                return owner
        return None

    async def get_by_id(self, owner_id: int) -> Owner | None:
        return self._owners.get(owner_id)

    async def get_by_uuid(self, uuid: str) -> Owner | None:
        return self._find_by(lambda o: o.uuid == uuid)

    async def get_by_user_id(self, user_id: int) -> Owner | None:
        return self._find_by(lambda o: o.user_id == user_id)

    async def create(self, owner: Owner) -> Owner:
        owner.id = self._next_id
        self._next_id += 1
        assert owner.id is not None
        owner.uuid = str(uuid_utils.uuid7())
        self._owners[owner.id] = owner
        return owner

    async def list_all(self, pagination: PaginationParams = PaginationParams()) -> tuple[list[Owner], int]:
        filtered = list(self._owners.values())
        total = len(filtered)
        return filtered[pagination.offset : pagination.offset + pagination.limit], total


@pytest.fixture
def owner_repo() -> InMemoryOwnerRepository:
    return InMemoryOwnerRepository()
