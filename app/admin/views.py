"""SQLAdmin model views.

One ``ModelView`` per registered persistence model. Views reference
*infrastructure* models only — domain entities, use cases, and events
are never involved (see ``app.admin`` package docstring for the rule).
"""

from typing import Any

from sqladmin import ModelView
from sqladmin.filters import BooleanFilter, StaticValuesFilter
from sqlalchemy import select
from starlette.requests import Request
from wtforms import PasswordField
from wtforms.validators import Optional

from app.admin.user_creation import AdminUserCreationError, ensure_unique_user_fields, prepare_new_user_data
from app.modules.car.infrastructure.persistence.models import CarModel
from app.modules.owner.infrastructure.persistence.models import OwnerModel
from app.modules.rbac.infrastructure.persistence.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserRoleModel,
)
from app.modules.user.domain.entities import UserStatus
from app.modules.user.infrastructure.persistence.models import UserModel

# Server/ORM-managed columns that must never appear on admin forms.
AUDIT_FORM_EXCLUDES = ["created_at", "updated_at", "deleted_at", "uuid"]

# User status choices exposed as a dropdown filter in the admin list view.
USER_STATUS_FILTER_VALUES = [(status.value, status.name.replace("_", " ").title()) for status in UserStatus]


class CarAdmin(ModelView, model=CarModel):
    name = "Car"
    name_plural = "Cars"
    icon = "fa-solid fa-car"

    column_list = [
        CarModel.id,
        CarModel.uuid,
        CarModel.make,
        CarModel.model,
        CarModel.year,
        CarModel.color,
        CarModel.license_plate,
        CarModel.owner_id,
    ]
    column_searchable_list = [CarModel.make, CarModel.model, CarModel.license_plate]
    column_sortable_list = [CarModel.id, CarModel.make, CarModel.model, CarModel.year]
    column_default_sort = (CarModel.id, True)
    column_filters = [
        CarModel.id,
        CarModel.owner_id,
        CarModel.make,
        CarModel.model,
        CarModel.year,
        CarModel.color,
        CarModel.license_plate,
        CarModel.created_at,
        CarModel.updated_at,
        CarModel.deleted_at,
    ]

    form_excluded_columns = AUDIT_FORM_EXCLUDES


class OwnerAdmin(ModelView, model=OwnerModel):
    name = "Owner"
    name_plural = "Owners"
    icon = "fa-solid fa-user-tie"

    column_list = [
        OwnerModel.id,
        OwnerModel.uuid,
        OwnerModel.user_id,
        OwnerModel.address,
        OwnerModel.date_of_birth,
        OwnerModel.cars,
    ]
    column_searchable_list = [OwnerModel.address]
    column_sortable_list = [OwnerModel.id, OwnerModel.user_id]
    column_default_sort = (OwnerModel.id, True)
    column_filters = [
        OwnerModel.id,
        OwnerModel.user_id,
        OwnerModel.address,
        OwnerModel.date_of_birth,
        OwnerModel.created_at,
        OwnerModel.updated_at,
        OwnerModel.deleted_at,
    ]

    # user_id is a deliberately bare cross-module FK (no ORM relationship —
    # owner must not couple to user at the ORM level). SQLAdmin skips bare
    # FK/PK columns in forms unless form_include_pk is set; enable it and
    # exclude the PK + audit columns explicitly.
    form_include_pk = True
    form_excluded_columns = [OwnerModel.id, *AUDIT_FORM_EXCLUDES, OwnerModel.cars]


class UserAdmin(ModelView, model=UserModel):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"

    column_list = [
        UserModel.id,
        UserModel.uuid,
        UserModel.email,
        UserModel.username,
        UserModel.phone_number,
        UserModel.first_name,
        UserModel.last_name,
        UserModel.status,
        UserModel.is_superuser,
    ]
    column_searchable_list = [UserModel.email, UserModel.username, UserModel.phone_number]
    column_sortable_list = [UserModel.id, UserModel.email, UserModel.username]
    column_default_sort = (UserModel.id, True)
    column_filters = [
        UserModel.id,
        UserModel.email,
        UserModel.username,
        UserModel.phone_number,
        UserModel.first_name,
        UserModel.last_name,
        StaticValuesFilter(UserModel.status, USER_STATUS_FILTER_VALUES),
        BooleanFilter(UserModel.is_superuser),
        UserModel.created_at,
        UserModel.updated_at,
        UserModel.deleted_at,
    ]

    # The password hash must never be displayed or editable through the admin.
    # (column_list above already omits it; details and forms exclude it too.)
    # "otps" is a backref from the otp module — excluded so the user form
    # never queries the otp table for select options at render time.
    form_excluded_columns = [*AUDIT_FORM_EXCLUDES, UserModel.hashed_password, "otps"]
    column_details_exclude_list = [UserModel.hashed_password, "otps"]

    # Creation is enabled through the custom insert_model below, which hashes
    # the plain password and reuses the domain validation rules. Deletion
    # stays disabled: removing users must follow the domain soft-delete flow.
    can_create = True
    can_delete = False

    async def scaffold_form(self, rules: list[str] | None = None) -> Any:
        """Add a non-model ``password`` field to the scaffolded form.

        WTForms only collects fields declared at class creation, so the
        field is injected by subclassing the scaffolded form. The field is
        Optional so the *edit* form is unaffected; it is required on create
        (enforced in ``prepare_new_user_data``).
        """
        base_form = await super().scaffold_form(rules)
        return type(
            "UserAdminForm",
            (base_form,),
            {
                "password": PasswordField(
                    "Password",
                    validators=[Optional()],
                    description=(
                        "Required when creating a user. Min 8 chars, one uppercase letter, "
                        "one special character. Ignored when editing."
                    ),
                )
            },
        )

    async def insert_model(self, request: Request, data: dict[str, Any]) -> Any:
        """Create a user with a properly hashed password and domain validation.

        Raises ``ValueError`` with a user-facing message on validation or
        uniqueness failures; SQLAdmin renders it as an alert on the form.
        """
        try:
            prepared = prepare_new_user_data(data)
            await ensure_unique_user_fields(prepared, self._field_value_exists)
        except AdminUserCreationError as exc:
            raise ValueError(str(exc)) from exc
        return await super().insert_model(request, prepared)

    async def update_model(self, request: Request, pk: str, data: dict[str, Any]) -> Any:
        """Edit a user. The optional password field is ignored on edits —
        password changes must go through the auth flows, not the admin."""
        data = dict(data)
        data.pop("password", None)
        return await super().update_model(request, pk, data)

    async def _field_value_exists(self, field: str, value: Any) -> bool:
        """Uniqueness lookup injected into ``ensure_unique_user_fields``."""
        async with self.session_maker() as session:
            stmt = select(UserModel.id).where(getattr(UserModel, field) == value)
            return (await session.execute(stmt)).scalar_one_or_none() is not None


class RoleAdmin(ModelView, model=RoleModel):
    name = "Role"
    name_plural = "Roles"
    icon = "fa-solid fa-users-gear"

    column_list = [RoleModel.id, RoleModel.uuid, RoleModel.name, RoleModel.description]
    column_searchable_list = [RoleModel.name]
    column_default_sort = (RoleModel.id, True)
    column_filters = [RoleModel.id, RoleModel.name, RoleModel.created_at, RoleModel.updated_at, RoleModel.deleted_at]

    form_excluded_columns = [*AUDIT_FORM_EXCLUDES]


class PermissionAdmin(ModelView, model=PermissionModel):
    name = "Permission"
    name_plural = "Permissions"
    icon = "fa-solid fa-key"

    column_list = [
        PermissionModel.id,
        PermissionModel.uuid,
        PermissionModel.name,
        PermissionModel.resource,
        PermissionModel.action,
        PermissionModel.description,
    ]
    column_searchable_list = [PermissionModel.name, PermissionModel.resource]
    column_sortable_list = [PermissionModel.id, PermissionModel.resource, PermissionModel.action]
    column_default_sort = (PermissionModel.id, True)
    column_filters = [
        PermissionModel.id,
        PermissionModel.name,
        PermissionModel.resource,
        PermissionModel.action,
        PermissionModel.created_at,
        PermissionModel.updated_at,
        PermissionModel.deleted_at,
    ]

    form_excluded_columns = [*AUDIT_FORM_EXCLUDES]


class UserRoleAdmin(ModelView, model=UserRoleModel):
    name = "User Role"
    name_plural = "User Roles"
    icon = "fa-solid fa-user-tag"

    column_list = [UserRoleModel.user_id, UserRoleModel.role_id, UserRoleModel.assigned_by, UserRoleModel.assigned_at]
    column_sortable_list = [UserRoleModel.user_id, UserRoleModel.role_id, UserRoleModel.assigned_at]
    column_filters = [
        UserRoleModel.user_id,
        UserRoleModel.role_id,
        UserRoleModel.assigned_by,
        UserRoleModel.assigned_at,
    ]


class RolePermissionAdmin(ModelView, model=RolePermissionModel):
    name = "Role Permission"
    name_plural = "Role Permissions"
    icon = "fa-solid fa-lock"

    column_list = [
        RolePermissionModel.role_id,
        RolePermissionModel.permission_id,
        RolePermissionModel.assigned_by,
        RolePermissionModel.assigned_at,
    ]
    column_sortable_list = [
        RolePermissionModel.role_id,
        RolePermissionModel.permission_id,
        RolePermissionModel.assigned_at,
    ]
    column_filters = [
        RolePermissionModel.role_id,
        RolePermissionModel.permission_id,
        RolePermissionModel.assigned_by,
        RolePermissionModel.assigned_at,
    ]
