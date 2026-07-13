"""Tests for OTP validation rate limiting."""

from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.cache import ICacheService
from app.main import app as fastapi_app
from app.modules.otp.api.dependencies import get_validate_otp_use_case
from app.modules.otp.domain.exceptions import InvalidOtpError
from app.modules.otp.use_cases.validate_otp import ValidateOtpUseCase


class _InMemoryCache(ICacheService):
    """Test cache that actually counts requests for rate-limit assertions."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def get(self, key: str) -> Any | None:
        return self._data.get(key)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._data

    async def incr(self, key: str) -> int:
        self._data[key] = self._data.get(key, 0) + 1
        return cast(int, self._data[key])

    async def set_ttl(self, key: str, value: Any, ttl: int) -> None:
        await self.set(key, value, ttl)


class _FakeValidateOtpUseCase:
    """Always rejects the code so the endpoint exercises the rate limiter."""

    async def execute(self, command: Any) -> None:
        raise InvalidOtpError("Invalid OTP code.")


def _fake_validate_use_case() -> ValidateOtpUseCase:
    return _FakeValidateOtpUseCase()  # type: ignore[return-value]


@pytest.fixture
def app() -> FastAPI:
    return fastapi_app


@pytest.mark.asyncio
async def test_otp_validation_rate_limited_per_user(app: FastAPI) -> None:
    """After 5 failed attempts per user, validation is blocked with 429."""
    app.state.security_cache_service = _InMemoryCache()
    app.dependency_overrides[get_validate_otp_use_case] = _fake_validate_use_case

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for attempt in range(5):
                response = await client.post(
                    "/api/v1/auth/otp/validate",
                    json={"user_uuid": "user-123", "otp_type": "login-otp", "code": "000000"},
                )
                assert response.status_code == 401, f"attempt {attempt + 1} should be 401"

            blocked = await client.post(
                "/api/v1/auth/otp/validate",
                json={"user_uuid": "user-123", "otp_type": "login-otp", "code": "000000"},
            )
            assert blocked.status_code == 429
            assert blocked.json()["errors"][0]["code"] == "RATE_LIMITED"
    finally:
        app.dependency_overrides.clear()
