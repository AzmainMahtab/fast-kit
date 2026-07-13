"""Root pytest configuration.

This module is imported automatically by pytest before any test modules.
It ensures that the test environment is configured even when no ``.env``
file is present, so the test suite can run in CI without local secrets.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-32-characters-long")
os.environ.setdefault("ENVIRONMENT", "test")
