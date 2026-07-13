from collections.abc import Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app
from app.modules.auth.api.dependencies import require_authenticated_user
from app.modules.rbac.api.dependencies import (
    get_assign_permission_use_case,
    get_assign_role_use_case,
    get_create_permission_use_case,
    get_create_role_use_case,
    get_list_permissions_use_case,
    get_list_roles_use_case,
)
from app.modules.rbac.tests.conftest import InMemoryRbacRepository
from app.modules.rbac.use_cases.assign_permission import AssignPermissionToRoleUseCase
from app.modules.rbac.use_cases.assign_role import AssignRoleUseCase
from app.modules.rbac.use_cases.create_permission import CreatePermissionUseCase
from app.modules.rbac.use_cases.create_role import CreateRoleUseCase
from app.modules.rbac.use_cases.list_permissions import ListPermissionsUseCase
from app.modules.rbac.use_cases.list_roles import ListRolesUseCase
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
def override_rbac_deps(app: FastAPI, rbac_repo: InMemoryRbacRepository) -> Generator[None]:
    app.dependency_overrides[get_create_permission_use_case] = lambda: CreatePermissionUseCase(rbac_repo=rbac_repo)
    app.dependency_overrides[get_create_role_use_case] = lambda: CreateRoleUseCase(rbac_repo=rbac_repo)
    app.dependency_overrides[get_list_permissions_use_case] = lambda: ListPermissionsUseCase(rbac_repo=rbac_repo)
    app.dependency_overrides[get_list_roles_use_case] = lambda: ListRolesUseCase(rbac_repo=rbac_repo)
    app.dependency_overrides[get_assign_permission_use_case] = lambda: AssignPermissionToRoleUseCase(
        rbac_repo=rbac_repo
    )
    app.dependency_overrides[get_assign_role_use_case] = lambda: AssignRoleUseCase(rbac_repo=rbac_repo)
    app.dependency_overrides[require_authenticated_user] = _mock_superuser
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_permission_returns_201(app, override_rbac_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rbac/permissions", json={"name": "owner:create", "resource": "owner", "action": "create"}
        )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["name"] == "owner:create"


@pytest.mark.asyncio
async def test_create_permission_returns_409_on_duplicate(app, override_rbac_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/rbac/permissions", json={"name": "owner:create", "resource": "owner", "action": "create"}
        )
        response = await client.post(
            "/api/v1/rbac/permissions", json={"name": "owner:create", "resource": "owner", "action": "create"}
        )

    assert response.status_code == 409
    body = response.json()
    assert body["errors"][0]["code"] == "PERMISSION_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_create_role_returns_201(app, override_rbac_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/rbac/roles", json={"name": "admin"})

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["name"] == "admin"


@pytest.mark.asyncio
async def test_assign_permission_to_role_returns_200(app, override_rbac_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        perm_resp = await client.post(
            "/api/v1/rbac/permissions", json={"name": "car:read", "resource": "car", "action": "read"}
        )
        perm_uuid = perm_resp.json()["data"]["uuid"]

        role_resp = await client.post("/api/v1/rbac/roles", json={"name": "manager"})
        role_uuid = role_resp.json()["data"]["uuid"]

        response = await client.post(f"/api/v1/rbac/roles/{role_uuid}/permissions", json={"permission_uuid": perm_uuid})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["message"] == "Permission assigned to role."


@pytest.mark.asyncio
async def test_list_permissions_returns_200(app, override_rbac_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/rbac/permissions", json={"name": "p1", "resource": "r", "action": "a"})
        await client.post("/api/v1/rbac/permissions", json={"name": "p2", "resource": "r", "action": "a"})

        response = await client.get("/api/v1/rbac/permissions")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] == 2


@pytest.mark.asyncio
async def test_list_roles_returns_200(app, override_rbac_deps) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/rbac/roles", json={"name": "role1"})
        await client.post("/api/v1/rbac/roles", json={"name": "role2"})

        response = await client.get("/api/v1/rbac/roles")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] == 2
