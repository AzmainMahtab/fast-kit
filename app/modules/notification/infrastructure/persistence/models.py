"""Notification SQLAlchemy models."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BaseModelMixin


class NotificationModel(BaseModelMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(32), default="")
    aggregate_id: Mapped[int | None] = mapped_column(nullable=True)
    message: Mapped[str] = mapped_column()
