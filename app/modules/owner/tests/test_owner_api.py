from collections.abc import Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app
from app.modules.auth.api.dependencies import require_authenticated_user
from app.modules.owner.api.dependencies import (
    get_create_owner_use_case,
    get_get_owner_use_case,
    get_list_owners_use_case,
)
from app.modules.owner.tests.conftest import InMemoryOwnerRepository
from app.modules.owner.use_cases.create_owner import CreateOwnerUseCase
from app.modules.owner.use_cases.get_owner import GetOwnerUseCase
from app.modules.owner.use_cases.list_owners import ListOwnersUseCase
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.value_objects import Email, HashedPassword, PhoneNumber


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
def override_owner_deps(app: FastAPI, owner_repo: InMemoryOwnerRepository) -> Generator[None]:
    app.dependency_overrides[get_create_owner_use_case] = lambda: CreateOwnerUseCase(owner_repo=owner_repo)
    app.dependency_overrides[get_get_owner_use_case] = lambda: GetOwnerUseCase(owner_repo=owner_repo)
    app.dependency_overrides[get_list_owners_use_case] = lambda: ListOwnersUseCase(owner_repo=owner_repo)
    app.dependency_overrides[require_authenticated_user] = _mock_superuser
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_owner_returns_201(app, override_owner_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/owners", json={"user_id": 1, "address": "123 Main St"})

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["statusCode"] == 201
    data = body["data"]
    assert data["user_id"] == 1
    assert data["address"] == "123 Main St"
    assert "uuid" in data


@pytest.mark.asyncio
async def test_create_owner_returns_409_on_duplicate(app, override_owner_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/owners", json={"user_id": 1, "address": "123 Main St"})
        response = await client.post("/api/v1/owners", json={"user_id": 1, "address": "456 Oak Ave"})

    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["errors"][0]["code"] == "OWNER_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_get_owner_by_uuid_returns_200(app, override_owner_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/owners", json={"user_id": 1, "address": "123 Main St"})
        uuid = create_resp.json()["data"]["uuid"]

        response = await client.get(f"/api/v1/owners/{uuid}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["uuid"] == uuid


@pytest.mark.asyncio
async def test_get_owner_by_uuid_returns_404(app, override_owner_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/owners/nonexistent-uuid")

    assert response.status_code == 404
    body = response.json()
    assert body["errors"][0]["code"] == "OWNER_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_owner_by_user_id_returns_200(app, override_owner_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/owners", json={"user_id": 1, "address": "123 Main St"})
        response = await client.get("/api/v1/owners/by-user/1")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["user_id"] == 1


@pytest.mark.asyncio
async def test_list_owners_returns_200(app, override_owner_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/owners", json={"user_id": 1, "address": "123 Main St"})
        await client.post("/api/v1/owners", json={"user_id": 2, "address": "456 Oak Ave"})

        response = await client.get("/api/v1/owners")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] == 2
    assert len(body["data"]["items"]) == 2
