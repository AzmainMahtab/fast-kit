import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core.cache import NullCache, RedisCache, create_redis_client
from app.core.database import AsyncSessionLocal
from app.core.event_bus import IEventBus, InMemoryEventBus
from app.core.nats_bus import NatsEventBus, create_event_bus
from app.core.exception_handlers import (
    app_exception_handler,
    auth_exception_handler,
    http_exception_handler,
    rbac_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.exceptions import AppException
from app.core.health import check_database, check_redis
from app.core.response import SuccessEnvelope
from app.core.seed import seed_superuser
from app.core.settings import settings
from app.modules.auth.api.router import router as auth_router
from app.modules.auth.domain.exception import AuthenticationError
from app.modules.auth.infrastructure.event_handlers import create_invalidate_user_caches_handler
from app.modules.car.api.router import router as car_router
from app.modules.notification.api.router import router as notification_router
from app.modules.notification.infrastructure.event_handlers import (
    create_session_repository_factory,
    subscribe_notification_handlers,
)
from app.modules.ordering.api.router import router as ordering_router
from app.modules.otp.api.router import router as otp_router
from app.modules.owner.api.router import router as owner_router
from app.modules.rbac.api.router import router as rbac_router
from app.modules.rbac.domain.exception import RbacError
from app.modules.user.api.router import router as user_router
from app.modules.user.domain.events import UserUpdatedEvent

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.event_bus = await create_event_bus()

    # Redis is required for security-critical features (token blacklists,
    # rate limiting, OTP state). In production we fail closed: if Redis is
    # unavailable the security cache is not initialized, so auth endpoints
    # return 503 instead of silently accepting revoked tokens or disabling
    # rate limits. In tests we allow a NullCache fallback.
    try:
        redis = await create_redis_client()
        await redis.ping()  # type: ignore[misc]
        app.state.cache_service = RedisCache(redis)
        app.state.security_cache_service = app.state.cache_service
    except Exception as exc:
        logger.warning("Redis unavailable: %s", exc)
        app.state.cache_service = NullCache()
        if settings.ENVIRONMENT == "test":
            app.state.security_cache_service = NullCache()
        else:
            # Intentionally leave security_cache_service unset so that any
            # auth/OTP/rate-limit path fails closed with 503.
            app.state.security_cache_service = None

    # Wire cross-module cache invalidation via domain events.
    # Auth module subscribes to user updates so it can clear its own caches
    # instead of having the user module delete auth cache keys directly.
    invalidate_handler = create_invalidate_user_caches_handler(app.state.cache_service)
    app.state.event_bus.subscribe(UserUpdatedEvent, invalidate_handler)

    # Wire notification module to ordering events.
    subscribe_notification_handlers(
        app.state.event_bus,
        create_session_repository_factory(AsyncSessionLocal),
    )

    await seed_superuser()

    yield
    if isinstance(app.state.event_bus, NatsEventBus):
        await app.state.event_bus.close()
    app.state.event_bus = None
    if isinstance(app.state.cache_service, RedisCache):
        await app.state.cache_service._client.close()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_exception_handler(AuthenticationError, auth_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)
app.add_exception_handler(RbacError, rbac_exception_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health", response_model=SuccessEnvelope[dict[str, str]], response_model_exclude_none=True, summary="Health check"
)
async def health() -> SuccessEnvelope[dict[str, str]]:
    db_ok = await check_database()
    redis_ok = await check_redis()
    return SuccessEnvelope(
        statusCode=200,
        data={"database": "ok" if db_ok else "unreachable", "redis": "ok" if redis_ok else "unreachable"},
    )


app.include_router(user_router, prefix=settings.API_V1_PREFIX)
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(otp_router, prefix=settings.API_V1_PREFIX)
app.include_router(owner_router, prefix=settings.API_V1_PREFIX)
app.include_router(car_router, prefix=settings.API_V1_PREFIX)
app.include_router(rbac_router, prefix=settings.API_V1_PREFIX)
app.include_router(ordering_router, prefix=settings.API_V1_PREFIX)
app.include_router(notification_router, prefix=settings.API_V1_PREFIX)
