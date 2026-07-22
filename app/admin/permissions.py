"""Admin access-control helpers.

Mirrors the permission-check pattern used by
``app.modules.auth.api.dependencies.require_permission``: superusers
bypass, everyone else needs the ``admin:access`` permission, and the
permission set is cached per user for 5 minutes.
"""

from app.core.cache import ICacheService
from app.modules.rbac.domain.interfaces import IRbacRepository
from app.modules.user.domain.entities import User

ADMIN_ACCESS_PERMISSION = "admin:access"
_PERMISSION_CACHE_TTL = 300


async def has_admin_access(user: User, rbac_repo: IRbacRepository, cache: ICacheService) -> bool:
    """Check whether a user may use the back-office admin.

    Args:
        user: The authenticated user's domain entity.
        rbac_repo: RBAC repository for permission lookups.
        cache: Security cache for per-user permission caching.

    Returns:
        True if the user is a superuser or holds ``admin:access``.
    """
    if user.is_superuser:
        return True

    if user.id is None:
        return False

    cache_key = f"user_permissions:{user.id}"
    cached_perms = await cache.get(cache_key)

    if cached_perms is not None:
        return ADMIN_ACCESS_PERMISSION in cached_perms

    perms = await rbac_repo.get_user_permissions(user.id)
    perm_names = [p.name for p in perms]
    await cache.set(cache_key, perm_names, ttl=_PERMISSION_CACHE_TTL)
    return ADMIN_ACCESS_PERMISSION in perm_names
