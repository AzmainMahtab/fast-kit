import asyncio
import os
from logging.config import fileConfig

# Load environment variables from .env file
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import your Base so Alembic can detect your models
from app.core.database import Base

# All models here for Alembic to detect. Import your models here.
from app.modules.car.infrastructure.persistence.models import CarModel  # noqa: F401
from app.modules.otp.infrastructure.persistence.models import OtpModel  # noqa: F401
from app.modules.owner.infrastructure.persistence.models import OwnerModel  # noqa: F401
from app.modules.user.infrastructure.persistence.models import UserModel  # noqa: F401

load_dotenv()

# Alembic Config object
config = context.config

# Set the SQLAlchemy URL from the environment variable
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL environment variable is not set. Check your .env file.")

# SETTING THE MAIN ASYNC DB URL
config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData target for 'autogenerate'
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"}
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode (async)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Wrapper to run async migrations."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
