"""Ordering SQLAlchemy models."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, BaseModelMixin


class OrderModel(BaseModelMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")

    jobs: Mapped[list["JobModel"]] = relationship(
        "JobModel",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class JobModel(BaseModelMixin, Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    job_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    file_editable: Mapped[bool] = mapped_column(default=True)

    order: Mapped["OrderModel"] = relationship("OrderModel", back_populates="jobs")
