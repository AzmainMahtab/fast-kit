import redis.asyncio as aioredis
from sqlalchemy import text

from app.core.database import engine
from app.core.settings import settings


async def check_database() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_redis() -> bool:
    try:
        client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        await client.execute_command("PING")  # type: ignore[no-untyped-call]
        await client.aclose()
        return True
    except Exception:
        return False
