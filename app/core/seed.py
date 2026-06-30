"""Startup seeding: create the first superuser from environment variables.

Runs inside the application lifespan before yielding to ensure the
superuser exists before the first request arrives.
"""

from app.core.database import AsyncSessionLocal
from app.core.hasher import get_password_hash
from app.core.settings import settings
from app.modules.user.domain.entities import User, UserStatus
from app.modules.user.domain.value_objects import Email, HashedPassword, PhoneNumber
from app.modules.user.infrastructure.persistence.repository import SQLAlchemyUserRepository


async def seed_superuser() -> None:
    """Create the first superuser if configured and not already present."""

    email = settings.FIRST_SUPERUSER_EMAIL
    password = settings.FIRST_SUPERUSER_PASSWORD
    username = getattr(settings, "FIRST_SUPERUSER_USERNAME", None)
    phone = getattr(settings, "FIRST_SUPERUSER_PHONE_NUMBER", None)

    if not email or not password:
        return

    async with AsyncSessionLocal() as session:
        repo = SQLAlchemyUserRepository(session)

        existing = await repo.get_by_email(Email(str(email)))
        if existing:
            return

        superuser = User(
            email=Email(str(email)),
            hashed_password=HashedPassword(get_password_hash(password)),
            username=username or "admin",
            phone_number=PhoneNumber(phone or "+1234567890"),
            first_name="Super",
            last_name="Admin",
            status=UserStatus.ACTIVE,
            is_superuser=True,
        )

        await repo.create(superuser)
        await session.commit()
