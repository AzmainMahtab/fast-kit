import pytest
import uuid_utils

from app.core.event_bus import InMemoryEventBus
from app.core.pagination import PaginationParams
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.interfaces import IUserRepository
from app.modules.user.domain.value_objects import Email


class InMemoryUserRepository(IUserRepository):
    def __init__(self) -> None:
        self._users: dict[int, User] = {}
        self._next_id = 1

    async def commit(self) -> None:
        """No-op for the in-memory test double."""
        return

    def _find_by(self, predicate) -> User | None:
        for user in self._users.values():
            if predicate(user):
                return user
        return None

    async def get_by_email(self, email: Email) -> User | None:
        return self._find_by(lambda u: u.email.value == email.value)

    async def get_by_id(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    async def get_by_uuid(self, uuid: str) -> User | None:
        return self._find_by(lambda u: u.uuid == uuid)

    async def get_by_username(self, username: str) -> User | None:
        return self._find_by(lambda u: u.username == username)

    async def create(self, user: User) -> User:
        user.id = self._next_id
        self._next_id += 1
        assert user.id is not None
        user.uuid = str(uuid_utils.uuid7())
        self._users[user.id] = user
        return user

    async def get_with_permissions(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    async def update(self, user: User) -> User:
        assert user.id is not None
        self._users[user.id] = user
        return user

    async def delete(self, uuid: str) -> None:
        user = self._find_by(lambda u: u.uuid == uuid)
        if user and user.id is not None:
            self._users.pop(user.id, None)

    async def list_all(
        self,
        status: UserStatus | None = None,
        include_deleted: bool = False,
        pagination: PaginationParams = PaginationParams(),
    ) -> tuple[list[User], int]:
        filtered = list(self._users.values())
        if not include_deleted:
            filtered = [u for u in filtered if u.deleted_at is None]
        if status:
            filtered = [u for u in filtered if u.status == status]
        total = len(filtered)
        return filtered[pagination.offset : pagination.offset + pagination.limit], total


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def user_repo() -> InMemoryUserRepository:
    return InMemoryUserRepository()
