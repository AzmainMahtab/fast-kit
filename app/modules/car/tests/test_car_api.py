from collections.abc import Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app
from app.modules.auth.api.dependencies import require_authenticated_user
from app.modules.car.api.dependencies import get_create_car_use_case, get_get_car_use_case, get_list_cars_use_case
from app.modules.car.tests.conftest import InMemoryCarRepository
from app.modules.car.use_cases.create_car import CreateCarUseCase
from app.modules.car.use_cases.get_car import GetCarUseCase
from app.modules.car.use_cases.list_cars import ListCarsUseCase
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
def override_car_deps(app: FastAPI, car_repo: InMemoryCarRepository) -> Generator[None]:
    app.dependency_overrides[get_create_car_use_case] = lambda: CreateCarUseCase(car_repo=car_repo)
    app.dependency_overrides[get_get_car_use_case] = lambda: GetCarUseCase(car_repo=car_repo)
    app.dependency_overrides[get_list_cars_use_case] = lambda: ListCarsUseCase(car_repo=car_repo)
    app.dependency_overrides[require_authenticated_user] = _mock_superuser
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_car_returns_201(app, override_car_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/cars",
            json={
                "owner_id": 1,
                "make": "Toyota",
                "model": "Camry",
                "year": 2023,
                "color": "Blue",
                "license_plate": "ABC-123",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["statusCode"] == 201
    data = body["data"]
    assert data["owner_id"] == 1
    assert data["make"] == "Toyota"
    assert data["license_plate"] == "ABC-123"
    assert "uuid" in data


@pytest.mark.asyncio
async def test_get_car_by_uuid_returns_200(app, override_car_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/v1/cars",
            json={
                "owner_id": 1,
                "make": "Toyota",
                "model": "Camry",
                "year": 2023,
                "color": "Blue",
                "license_plate": "ABC-123",
            },
        )
        uuid = create_resp.json()["data"]["uuid"]

        response = await client.get(f"/api/v1/cars/{uuid}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["uuid"] == uuid


@pytest.mark.asyncio
async def test_get_car_by_uuid_returns_404(app, override_car_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/cars/nonexistent-uuid")

    assert response.status_code == 404
    body = response.json()
    assert body["errors"][0]["code"] == "CAR_NOT_FOUND"


@pytest.mark.asyncio
async def test_list_cars_by_owner_returns_200(app, override_car_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/cars",
            json={
                "owner_id": 1,
                "make": "Toyota",
                "model": "Camry",
                "year": 2023,
                "color": "Blue",
                "license_plate": "P1",
            },
        )
        await client.post(
            "/api/v1/cars",
            json={
                "owner_id": 1,
                "make": "Honda",
                "model": "Civic",
                "year": 2022,
                "color": "Red",
                "license_plate": "P2",
            },
        )
        await client.post(
            "/api/v1/cars",
            json={
                "owner_id": 2,
                "make": "Ford",
                "model": "F-150",
                "year": 2021,
                "color": "Black",
                "license_plate": "P3",
            },
        )

        response = await client.get("/api/v1/cars/by-owner/1")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] == 2
    assert len(body["data"]["items"]) == 2


@pytest.mark.asyncio
async def test_list_all_cars_returns_200(app, override_car_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/cars",
            json={
                "owner_id": 1,
                "make": "Toyota",
                "model": "Camry",
                "year": 2023,
                "color": "Blue",
                "license_plate": "P1",
            },
        )
        await client.post(
            "/api/v1/cars",
            json={
                "owner_id": 2,
                "make": "Honda",
                "model": "Civic",
                "year": 2022,
                "color": "Red",
                "license_plate": "P2",
            },
        )

        response = await client.get("/api/v1/cars")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] == 2
