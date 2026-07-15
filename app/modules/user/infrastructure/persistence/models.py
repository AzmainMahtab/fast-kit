import uuid_utils
from sqlalchemy import UUID, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BaseModelMixin


class UserModel(BaseModelMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid_utils.uuid7,
        server_default=func.uuid_generate_v7(),
    )
    # Mirrors the legacy Elite4Print user UUID so migrated slice data can reference
    # the original identifier without changing the internal integer PK used by RBAC.
    legacy_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=True, index=True
    )

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending_verification")
    is_superuser: Mapped[bool] = mapped_column(default=False, nullable=False)

