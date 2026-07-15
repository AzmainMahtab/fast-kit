"""Startup seeding: create the first superuser, RBAC permissions, roles, and assignments.

Runs inside the application lifespan before yielding to ensure the
superuser and full RBAC hierarchy exist before the first request arrives.
"""

from app.core.database import AsyncSessionLocal
from app.core.hasher import get_password_hash
from app.core.settings import settings
from app.modules.rbac.domain.entities import Permission, Role
from app.modules.rbac.infrastructure.persistence.repository import SQLAlchemyRbacRepository
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.value_objects import Email, HashedPassword, PhoneNumber
from app.modules.user.infrastructure.persistence.repository import SQLAlchemyUserRepository

# All permissions referenced by require_permission(...) guards in the codebase.
# Format: resource:action — kept in sync with router decorators.
_SEED_PERMISSIONS: list[tuple[str, str, str]] = [
    # RBAC management
    ("rbac:permission:create", "rbac", "create"),
    ("rbac:permission:list", "rbac", "list"),
    ("rbac:role:create", "rbac", "create"),
    ("rbac:role:list", "rbac", "list"),
    ("rbac:role:read", "rbac", "read"),
    ("rbac:role:assign_permission", "rbac", "assign_permission"),
    ("rbac:role:revoke_permission", "rbac", "revoke_permission"),
    ("rbac:role:read_permissions", "rbac", "read_permissions"),
    ("rbac:role:assign_user", "rbac", "assign_user"),
    ("rbac:role:revoke_user", "rbac", "revoke_user"),
    ("rbac:user:read_permissions", "rbac", "read_permissions"),
    ("rbac:user:read_roles", "rbac", "read_roles"),
    ("rbac:user:check_permission", "rbac", "check_permission"),
    # User module
    ("user:create", "user", "create"),
    ("user:read", "user", "read"),
    ("user:update", "user", "update"),
    ("user:delete", "user", "delete"),
    # Owner module
    ("owner:create", "owner", "create"),
    ("owner:read", "owner", "read"),
    # Car module
    ("car:create", "car", "create"),
    ("car:read", "car", "read"),
]

_SUPERADMIN_ROLE_NAME = "superadmin"


async def seed_superuser() -> None:
    """Bootstrap the entire RBAC system and first superuser.

    Idempotent: safely re-runs on every startup. Skips anything that
    already exists.
    """
    email = settings.FIRST_SUPERUSER_EMAIL
    password = settings.FIRST_SUPERUSER_PASSWORD
    username = settings.FIRST_SUPERUSER_USERNAME
    phone = settings.FIRST_SUPERUSER_PHONE_NUMBER

    if not email or not password:
        return

    async with AsyncSessionLocal() as session:
        user_repo = SQLAlchemyUserRepository(session)
        rbac_repo = SQLAlchemyRbacRepository(session)

        # 1. Seed permissions (idempotent)
        permission_map: dict[str, Permission] = {}
        for name, resource, action in _SEED_PERMISSIONS:
            existing = await rbac_repo.get_permission_by_name(name)
            if existing:
                permission_map[name] = existing
            else:
                perm = await rbac_repo.create_permission(Permission(name=name, resource=resource, action=action))
                permission_map[name] = perm

        # 2. Seed superadmin role (idempotent)
        superadmin_role = await rbac_repo.get_role_by_name(_SUPERADMIN_ROLE_NAME)
        if not superadmin_role:
            superadmin_role = await rbac_repo.create_role(
                Role(name=_SUPERADMIN_ROLE_NAME, description="Full system access.")
            )

        # 3. Assign all permissions to superadmin role (idempotent)
        if superadmin_role.id is None:
            raise RuntimeError("Superadmin role was not assigned an identifier.")
        for perm in permission_map.values():
            if perm.id is None:
                continue
            await rbac_repo.assign_permission_to_role(superadmin_role.id, perm.id)

        # 4. Seed superuser (idempotent by email or username)
        email_vo = Email(str(email))
        superuser = await user_repo.get_by_email(email_vo)
        if not superuser and username:
            superuser = await user_repo.get_by_username(username)
        if not superuser:
            superuser = User(
                email=email_vo,
                hashed_password=HashedPassword(get_password_hash(password)),
                username=username or "admin",
                phone_number=PhoneNumber(phone or "+1234567890"),
                first_name="Super",
                last_name="Admin",
                status=UserStatus.ACTIVE,
                is_superuser=True,
            )
            superuser = await user_repo.create(superuser)

        # 5. Assign superadmin role to superuser (idempotent)
        if superuser.id is None:
            raise RuntimeError("Superuser was not assigned an identifier.")
        await rbac_repo.assign_role_to_user(superuser.id, superadmin_role.id)

        await session.commit()
