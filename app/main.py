from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core.cache import NullCache, RedisCache, create_redis_client
from app.core.event_bus import InMemoryEventBus
from app.core.exception_handlers import (
    app_exception_handler,
    auth_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.exceptions import AppException
from app.core.health import check_database, check_redis
from app.core.response import SuccessEnvelope
from app.core.settings import settings
from app.modules.auth.api.router import router as auth_router
from app.modules.auth.domain.events import UserLoggedInEvent
from app.modules.auth.domain.exception import AuthenticationError
from app.modules.auth.infrastructure.event_handlers import create_invalidate_user_caches_handler
from app.modules.car.api.router import router as car_router
from app.modules.otp.api.router import router as otp_router
from app.modules.otp.infrastructure.event_handlers import create_generate_login_otp_handler
from app.modules.owner.api.router import router as owner_router
from app.modules.user.api.router import router as user_router
from app.modules.user.domain.events import UserUpdatedEvent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.event_bus = InMemoryEventBus()
    try:
        redis = await create_redis_client()
        await redis.ping()
        app.state.cache_service = RedisCache(redis)
    except Exception:
        app.state.cache_service = NullCache()

    # Wire cross-module cache invalidation via domain events.
    # Auth module subscribes to user updates so it can clear its own caches
    # instead of having the user module delete auth cache keys directly.
    invalidate_handler = create_invalidate_user_caches_handler(app.state.cache_service)
    app.state.event_bus.subscribe(UserUpdatedEvent, invalidate_handler)

    # OTP module subscribes to auth login events to generate login OTPs
    # automatically on every successful authentication.
    login_otp_handler = create_generate_login_otp_handler(app.state.cache_service, app.state.event_bus)
    app.state.event_bus.subscribe(UserLoggedInEvent, login_otp_handler)

    yield
    app.state.event_bus = None
    if isinstance(app.state.cache_service, RedisCache):
        await app.state.cache_service._client.close()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_exception_handler(AuthenticationError, auth_exception_handler)
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=SuccessEnvelope[dict], response_model_exclude_none=True, summary="Health check")
async def health():
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
