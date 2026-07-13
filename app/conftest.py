"""Root pytest configuration.

This module is imported automatically by pytest before any test modules.
It ensures that the test environment is configured even when no ``.env``
file is present, so the test suite can run in CI without local secrets.
"""

import os

import pytest

from app.core.cache import NullCache
from app.main import app

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-32-characters-long")
os.environ.setdefault("ENVIRONMENT", "test")


@pytest.fixture(autouse=True)
def _configure_test_app_state() -> None:
    """Provide a NullCache fallback for the security cache in unit tests.

    The real application does not fall back to NullCache for security-critical
    paths, but unit tests that bypass the lifespan need cache state initialized.
    """
    app.state.cache_service = NullCache()
    app.state.security_cache_service = NullCache()
