"""Tests for admin assembly: view registration and safety rails.

No database is touched — registration is pure configuration.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from sqladmin import ModelView
from sqladmin.filters import BooleanFilter, StaticValuesFilter

from app.admin.setup import create_admin
from app.admin.views import (
    CarAdmin,
    OwnerAdmin,
    PermissionAdmin,
    RoleAdmin,
    RolePermissionAdmin,
    UserAdmin,
    UserRoleAdmin,
)
from app.modules.car.infrastructure.persistence.models import CarModel
from app.modules.owner.infrastructure.persistence.models import OwnerModel
from app.modules.rbac.infrastructure.persistence.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserRoleModel,
)
from app.modules.user.infrastructure.persistence.models import UserModel


def test_create_admin_registers_all_views() -> None:
    app = FastAPI()
    admin = create_admin(app)

    registered_models = {view.model for view in admin._views if isinstance(view, ModelView)}
    assert registered_models == {
        CarModel,
        OwnerModel,
        UserModel,
        RoleModel,
        PermissionModel,
        UserRoleModel,
        RolePermissionModel,
    }


def test_admin_is_mounted_at_admin_path() -> None:
    app = FastAPI()
    create_admin(app)

    admin_paths = {getattr(route, "path", "") for route in app.routes}
    assert "/admin" in admin_paths or any(p.startswith("/admin") for p in admin_paths)


class TestUserAdminSafetyRails:
    """User creation is allowed only through the custom insert_model
    (hashed password + domain validation); deletion stays disabled; the
    password hash must never leak into any admin surface."""

    def test_user_creation_enabled_via_custom_insert(self) -> None:
        assert UserAdmin.can_create is True

    def test_user_deletion_disabled(self) -> None:
        assert UserAdmin.can_delete is False

    def test_password_hash_excluded_from_forms(self) -> None:
        excluded = {getattr(col, "key", col) for col in UserAdmin.form_excluded_columns}
        assert "hashed_password" in excluded

    def test_password_hash_excluded_from_list_and_details(self) -> None:
        listed = {getattr(col, "key", col) for col in UserAdmin.column_list}
        detailed = {getattr(col, "key", col) for col in UserAdmin.column_details_exclude_list}
        assert "hashed_password" not in listed
        assert "hashed_password" in detailed


class TestUserAdminForm:
    """The scaffolded user form gains a plain ``password`` field while the
    stored hash stays off every form."""

    async def _scaffolded_user_form(self) -> Any:
        app = FastAPI()
        admin = create_admin(app)
        view = next(v for v in admin._views if isinstance(v, UserAdmin))
        return await view.scaffold_form()

    async def test_form_contains_password_field(self) -> None:
        form_class = await self._scaffolded_user_form()
        field_names = {name for name, _field in form_class()._fields.items()}

        assert "password" in field_names

    async def test_form_never_contains_password_hash(self) -> None:
        form_class = await self._scaffolded_user_form()
        field_names = {name for name, _field in form_class()._fields.items()}

        assert "hashed_password" not in field_names


def _filter_keys(column_filters: list[Any]) -> set[str]:
    """Return the column keys represented by a list of SQLAdmin filters."""
    keys: set[str] = set()
    for item in column_filters:
        if isinstance(item, (BooleanFilter, StaticValuesFilter)):
            keys.add(getattr(item.column, "key", item.column))
        else:
            keys.add(getattr(item, "key", item))
    return keys


class TestAdminColumnFilters:
    """Every model view should expose per-column filters on the list page."""

    @pytest.mark.parametrize(
        "view_class, expected",
        [
            (
                CarAdmin,
                {
                    "id",
                    "owner_id",
                    "make",
                    "model",
                    "year",
                    "color",
                    "license_plate",
                    "created_at",
                    "updated_at",
                    "deleted_at",
                },
            ),
            (OwnerAdmin, {"id", "user_id", "address", "date_of_birth", "created_at", "updated_at", "deleted_at"}),
            (
                UserAdmin,
                {
                    "id",
                    "email",
                    "username",
                    "phone_number",
                    "first_name",
                    "last_name",
                    "status",
                    "is_superuser",
                    "created_at",
                    "updated_at",
                    "deleted_at",
                },
            ),
            (RoleAdmin, {"id", "name", "created_at", "updated_at", "deleted_at"}),
            (PermissionAdmin, {"id", "name", "resource", "action", "created_at", "updated_at", "deleted_at"}),
            (UserRoleAdmin, {"user_id", "role_id", "assigned_by", "assigned_at"}),
            (RolePermissionAdmin, {"role_id", "permission_id", "assigned_by", "assigned_at"}),
        ],
    )
    def test_view_has_column_filters(self, view_class: type[ModelView], expected: set[str]) -> None:
        assert hasattr(view_class, "column_filters")
        assert _filter_keys(view_class.column_filters) == expected

    def test_user_status_uses_static_values_filter(self) -> None:
        status_filter = next(
            f
            for f in UserAdmin.column_filters
            if isinstance(f, StaticValuesFilter) and getattr(f.column, "key", None) == "status"
        )
        assert {value for value, _label in status_filter.values} == {
            "pending_verification",
            "active",
            "inactive",
            "suspended",
        }

    def test_user_is_superuser_uses_boolean_filter(self) -> None:
        assert any(
            isinstance(f, BooleanFilter) and getattr(f.column, "key", None) == "is_superuser"
            for f in UserAdmin.column_filters
        )
