"""Tests for event store and dead-letter admin APIs."""

import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app
from app.modules.auth.api.dependencies import require_authenticated_user
from app.modules.event_outbox.api.dependencies import get_event_bus, get_outbox_repo
from app.modules.event_outbox.domain.interfaces import IOutboxRepository
from app.modules.event_outbox.tests.conftest import InMemoryOutboxRepository
from app.modules.ordering.domain.events import OrderCreated
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.value_objects import Email, HashedPassword, PhoneNumber

ORDER_CREATED_CLASS_PATH = f"{OrderCreated.__module__}.{OrderCreated.__qualname__}"


def _mock_superuser() -> User:
    return User(
        id=1,
        uuid="mock-user-uuid",
        email=Email("mock@example.com"),
        hashed_password=HashedPassword("mock"),
        username="mockuser",
        phone_number=PhoneNumber("+1234567890"),
        is_superuser=True,
        status=UserStatus.ACTIVE,
    )


@pytest.fixture
def app() -> FastAPI:
    return fastapi_app


@pytest.fixture
def outbox_repo() -> InMemoryOutboxRepository:
    return InMemoryOutboxRepository()


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def override_event_outbox_deps(
    app: FastAPI, outbox_repo: IOutboxRepository, mock_event_bus: AsyncMock
) -> Generator[None]:
    app.dependency_overrides[get_outbox_repo] = lambda: outbox_repo
    app.dependency_overrides[get_event_bus] = lambda: mock_event_bus
    app.dependency_overrides[require_authenticated_user] = _mock_superuser
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_events_returns_200(
    app: FastAPI, outbox_repo: InMemoryOutboxRepository, override_event_outbox_deps
) -> None:
    await outbox_repo.add_event_store(
        None,
        event_type="OrderCreated",
        event_class_path=ORDER_CREATED_CLASS_PATH,
        payload={"order_id": 1, "order_number": "ORD-001", "user_id": 1, "job_ids": ["job-1"]},
        aggregate_id="1",
        correlation_id=None,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/events")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["event_type"] == "OrderCreated"


@pytest.mark.asyncio
async def test_get_event_returns_200(
    app: FastAPI, outbox_repo: InMemoryOutboxRepository, override_event_outbox_deps
) -> None:
    event = await outbox_repo.add_event_store(
        None,
        event_type="OrderCreated",
        event_class_path=ORDER_CREATED_CLASS_PATH,
        payload={"order_id": 1, "order_number": "ORD-001", "user_id": 1, "job_ids": ["job-1"]},
        aggregate_id="1",
        correlation_id=None,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/admin/events/{event.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == str(event.id)
    assert body["data"]["payload"] == {
        "order_id": 1,
        "order_number": "ORD-001",
        "user_id": 1,
        "job_ids": ["job-1"],
    }


@pytest.mark.asyncio
async def test_get_event_returns_404(
    app: FastAPI, override_event_outbox_deps
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/admin/events/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_replay_event_returns_200(
    app: FastAPI, outbox_repo: InMemoryOutboxRepository, mock_event_bus: AsyncMock, override_event_outbox_deps
) -> None:
    event = await outbox_repo.add_event_store(
        None,
        event_type="OrderCreated",
        event_class_path=ORDER_CREATED_CLASS_PATH,
        payload={"order_id": 1, "order_number": "ORD-001", "user_id": 1, "job_ids": ["job-1"]},
        aggregate_id="1",
        correlation_id=None,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/admin/events/{event.id}/replay")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["republished"] is True
    assert body["data"]["subject"] == "events.ordering.order_created"
    mock_event_bus.publish_raw.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_dead_letter_events_returns_200(
    app: FastAPI, outbox_repo: InMemoryOutboxRepository, override_event_outbox_deps
) -> None:
    await outbox_repo.add_dead_letter(
        None,
        event_class_path=ORDER_CREATED_CLASS_PATH,
        payload={"order_id": 1, "order_number": "ORD-001", "user_id": 1, "job_ids": ["job-1"]},
        subject="events.ordering.order_created",
        error_message="handler failed",
        attempts=3,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/dead-letter-events")

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["error_message"] == "handler failed"


@pytest.mark.asyncio
async def test_replay_dead_letter_event_returns_200(
    app: FastAPI, outbox_repo: InMemoryOutboxRepository, mock_event_bus: AsyncMock, override_event_outbox_deps
) -> None:
    row = await outbox_repo.add_dead_letter(
        None,
        event_class_path=ORDER_CREATED_CLASS_PATH,
        payload={"order_id": 1, "order_number": "ORD-001", "user_id": 1, "job_ids": ["job-1"]},
        subject="events.ordering.order_created",
        error_message="handler failed",
        attempts=3,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/admin/dead-letter-events/{row.id}/replay")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["republished"] is True
    mock_event_bus.publish_raw.assert_awaited_once()

    resolved_row = await outbox_repo.get_dead_letter(None, row.id)
    assert resolved_row is not None
    assert resolved_row.resolved_at is not None


@pytest.mark.asyncio
async def test_resolve_dead_letter_event_returns_200(
    app: FastAPI, outbox_repo: InMemoryOutboxRepository, override_event_outbox_deps
) -> None:
    row = await outbox_repo.add_dead_letter(
        None,
        event_class_path=ORDER_CREATED_CLASS_PATH,
        payload={"order_id": 1, "order_number": "ORD-001", "user_id": 1, "job_ids": ["job-1"]},
        subject="events.ordering.order_created",
        error_message="handler failed",
        attempts=3,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/admin/dead-letter-events/{row.id}/resolve")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["resolved"] is True

    resolved_row = await outbox_repo.get_dead_letter(None, row.id)
    assert resolved_row is not None
    assert resolved_row.resolved_at is not None


@pytest.mark.asyncio
async def test_resolve_dead_letter_event_returns_404(
    app: FastAPI, override_event_outbox_deps
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/admin/dead-letter-events/{uuid.uuid4()}/resolve")

    assert response.status_code == 404
