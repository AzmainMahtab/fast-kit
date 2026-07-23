"""Factory that attaches the SQLAdmin back-office to the FastAPI app.

Kept as a single function so ``app.main`` needs exactly one line of
integration, and so tests can build an admin instance against their own
app/engine without touching the production one.
"""

from fastapi import FastAPI
from sqladmin import Admin
from sqlalchemy.ext.asyncio import AsyncEngine

from app.admin.auth import AdminAuthBackend
from app.admin.views import (
    CarAdmin,
    OwnerAdmin,
    PermissionAdmin,
    RoleAdmin,
    RolePermissionAdmin,
    UserAdmin,
    UserRoleAdmin,
)
from app.core.database import engine as default_engine
from app.core.settings import settings

_ALL_VIEWS = [CarAdmin, OwnerAdmin, UserAdmin, RoleAdmin, PermissionAdmin, UserRoleAdmin, RolePermissionAdmin]


def create_admin(
    app: FastAPI, engine: AsyncEngine = default_engine, authentication_backend: AdminAuthBackend | None = None
) -> Admin:
    """Create and attach the SQLAdmin interface to the application.

    Args:
        app: The FastAPI application.
        engine: Async SQLAlchemy engine the admin queries through.
        authentication_backend: Optional pre-built auth backend (tests
            inject one with in-memory dependencies).

    Returns:
        The configured ``Admin`` instance.
    """
    # The cache getter closes over the *real* FastAPI app: inside SQLAdmin's
    # mounted sub-app, request.app is the sub-app, so the backend cannot read
    # the security cache from request.app.state. Evaluated per request, after
    # the lifespan has populated app.state.
    backend = authentication_backend or AdminAuthBackend(
        secret_key=settings.JWT_SECRET_KEY, cache_getter=lambda: getattr(app.state, "security_cache_service", None)
    )
    admin = Admin(app=app, engine=engine, title=f"{settings.PROJECT_NAME} Admin", authentication_backend=backend)
    for view in _ALL_VIEWS:
        admin.add_view(view)
    return admin
