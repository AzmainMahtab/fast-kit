"""Tests for cache service dependency behavior.

Production security-critical paths must fail closed when Redis is
unavailable instead of silently degrading to a no-op cache.
"""

from typing import Any

import pytest

from app.core.cache import NullCache, get_cache_service, get_security_cache_service
from app.core.exceptions import AppException


class _FakeApp:
    def __init__(self) -> None:
        self.state: Any = object()


class _FakeRequest:
    def __init__(self, state: Any) -> None:
        self.app = _FakeApp()
        self.app.state = state


def test_get_cache_service_returns_null_when_missing() -> None:
    """Non-security cache may degrade gracefully to NullCache."""
    request = _FakeRequest(state=object())
    cache = get_cache_service(request)  # type: ignore[arg-type]
    assert isinstance(cache, NullCache)


def test_get_security_cache_service_raises_when_unavailable() -> None:
    """Security cache must not silently degrade to NullCache."""
    request = _FakeRequest(state=object())
    with pytest.raises(AppException) as exc_info:
        get_security_cache_service(request)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "SECURITY_CACHE_UNAVAILABLE"
