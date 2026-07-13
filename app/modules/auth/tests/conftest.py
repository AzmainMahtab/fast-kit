from uuid import uuid4

import pytest
import pytest_asyncio

from app.core.cache import NullCache
from app.core.event_bus import InMemoryEventBus
from app.core.jwt import JWTService
from app.core.pagination import PaginationParams
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.interfaces import IUserRepository
from app.modules.user.domain.value_objects import Email, HashedPassword, PhoneNumber


class InMemoryUserRepository(IUserRepository):
    """Minimal in-memory user repository for auth tests.

    Supports the subset of ``IUserRepository`` methods needed by auth use cases.
    """

    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    async def commit(self) -> None:
        """No-op for the in-memory test double."""
        return

    async def get_by_uuid(self, uuid: str) -> User | None:
        return self._users.get(uuid)

    async def get_by_email(self, email: Email) -> User | None:
        for user in self._users.values():
            if user.email.value == email.value:
                return user
        return None

    async def update(self, user: User) -> User:
        assert user.uuid is not None
        self._users[user.uuid] = user
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        return None

    async def get_by_username(self, username: str) -> User | None:
        return None

    async def create(self, user: User) -> User:
        user.uuid = str(uuid4())
        self._users[user.uuid] = user
        return user

    async def delete(self, uuid: str) -> None:
        self._users.pop(uuid, None)

    async def list_all(
        self,
        status: UserStatus | None = None,
        include_deleted: bool = False,
        pagination: PaginationParams = PaginationParams(),
    ) -> tuple[list[User], int]:
        items = list(self._users.values())
        if not include_deleted:
            items = [u for u in items if u.deleted_at is None]
        if status:
            items = [u for u in items if u.status == status]
        total = len(items)
        return items[pagination.offset : pagination.offset + pagination.limit], total


DEFAULT_PASSWORD = "$argon2id$v=19$m=65536,t=3,p=4$..."  # placeholder hash


def make_user(
    uuid: str | None = None,
    email: str = "test@example.com",
    password: str | None = None,
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    return User(
        uuid=uuid or str(uuid4()),
        email=Email(email),
        hashed_password=HashedPassword(password or DEFAULT_PASSWORD),
        username="testuser",
        phone_number=PhoneNumber("+1234567890"),
        first_name="Test",
        last_name="User",
        status=status,
    )


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def cache() -> NullCache:
    return NullCache()


@pytest.fixture
def jwt_service() -> JWTService:
    return JWTService(secret_key="test-secret-key-for-testing-only")


@pytest_asyncio.fixture
async def user_repo() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest_asyncio.fixture
async def active_user(user_repo: InMemoryUserRepository) -> User:
    user = make_user(email="active@example.com", status=UserStatus.ACTIVE)
    return await user_repo.create(user)


@pytest_asyncio.fixture
async def suspended_user(user_repo: InMemoryUserRepository) -> User:
    user = make_user(email="suspended@example.com", status=UserStatus.SUSPENDED)
    return await user_repo.create(user)


@pytest_asyncio.fixture
async def inactive_user(user_repo: InMemoryUserRepository) -> User:
    user = make_user(email="inactive@example.com", status=UserStatus.INACTIVE)
    return await user_repo.create(user)
