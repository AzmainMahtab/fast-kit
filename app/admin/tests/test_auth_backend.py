"""HTTP-flow tests for AdminAuthBackend — the SQLAdmin session-cookie adapter.

Hermetic: the authenticator is stubbed and the session factory yields a
dummy, so no database or Redis is touched. These tests verify the cookie
session mechanics end to end through the real SQLAdmin login/logout views.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqladmin import Admin

from app.admin.auth import AdminAuthBackend
from app.admin.tests.conftest import TEST_PASSWORD, make_user
from app.core.cache import NullCache
from app.core.database import engine

REDIRECT_CODES = {302, 303, 307}


class StubAuthenticator:
    """Canned verification results, keyed by password."""

    def __init__(self, user=None) -> None:
        self._user = user
        self.login_calls: list[tuple[str, str]] = []
        self.session_calls: list[str] = []

    async def verify_login(self, email: str, password: str):
        self.login_calls.append((email, password))
        if self._user is not None and password == TEST_PASSWORD:
            return self._user
        return None

    async def verify_session(self, user_uuid: str):
        self.session_calls.append(user_uuid)
        if self._user is not None and user_uuid == str(self._user.uuid):
            return self._user
        return None


@asynccontextmanager
async def _fake_session() -> AsyncGenerator[object]:
    yield object()


def _build_app(authenticator: StubAuthenticator, with_cache: bool = True) -> FastAPI:
    app = FastAPI()
    backend = AdminAuthBackend(
        secret_key="test-secret-key-that-is-32-characters-long",
        session_factory=_fake_session,  # type: ignore[arg-type]
        authenticator_factory=lambda session, cache: authenticator,  # type: ignore[arg-type, return-value]
        cache_getter=lambda: NullCache() if with_cache else None,
    )
    Admin(app=app, engine=engine, authentication_backend=backend)
    return app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    app = _build_app(StubAuthenticator(user=make_user(is_superuser=True)))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestLoginFlow:
    async def test_login_page_renders(self, client: AsyncClient) -> None:
        response = await client.get("/admin/login")
        assert response.status_code == 200

    async def test_valid_credentials_establish_session(self, client: AsyncClient) -> None:
        response = await client.post(
            "/admin/login", data={"username": "admin@example.com", "password": TEST_PASSWORD}, follow_redirects=False
        )
        assert response.status_code in REDIRECT_CODES
        assert "/admin" in response.headers["location"]

        # The session cookie now authenticates subsequent admin requests.
        index = await client.get("/admin/", follow_redirects=False)
        assert index.status_code == 200

    async def test_invalid_credentials_are_rejected(self, client: AsyncClient) -> None:
        response = await client.post(
            "/admin/login", data={"username": "admin@example.com", "password": "wrong"}, follow_redirects=False
        )
        assert response.status_code == 400

        index = await client.get("/admin/", follow_redirects=False)
        assert index.status_code in REDIRECT_CODES
        assert "/admin/login" in index.headers["location"]

    async def test_unauthenticated_request_redirects_to_login(self) -> None:
        app = _build_app(StubAuthenticator(user=make_user(is_superuser=True)))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            index = await c.get("/admin/", follow_redirects=False)
        assert index.status_code in REDIRECT_CODES
        assert "/admin/login" in index.headers["location"]


class TestLogout:
    async def test_logout_clears_session(self, client: AsyncClient) -> None:
        await client.post(
            "/admin/login", data={"username": "admin@example.com", "password": TEST_PASSWORD}, follow_redirects=False
        )
        assert (await client.get("/admin/", follow_redirects=False)).status_code == 200

        await client.get("/admin/logout", follow_redirects=False)

        index = await client.get("/admin/", follow_redirects=False)
        assert index.status_code in REDIRECT_CODES
        assert "/admin/login" in index.headers["location"]


class TestFailClosed:
    async def test_login_fails_closed_without_security_cache(self) -> None:
        """No security cache (e.g. Redis down in prod) -> login denied, not bypassed."""
        app = _build_app(StubAuthenticator(user=make_user(is_superuser=True)), with_cache=False)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.post(
                "/admin/login",
                data={"username": "admin@example.com", "password": TEST_PASSWORD},
                follow_redirects=False,
            )
        assert response.status_code == 400


class TestSessionContents:
    async def test_session_round_trips_only_user_uuid(self) -> None:
        """The cookie must carry only the user uuid — no credentials, no permissions."""
        stub = StubAuthenticator(user=make_user(is_superuser=True))
        app = _build_app(stub)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.post(
                "/admin/login",
                data={"username": "admin@example.com", "password": TEST_PASSWORD},
                follow_redirects=False,
            )
            # A later request resolves identity via verify_session with the
            # uuid taken from the signed cookie.
            assert stub.session_calls == []
            await c.get("/admin/", follow_redirects=False)
            assert stub.session_calls == ["user-uuid-1"]
