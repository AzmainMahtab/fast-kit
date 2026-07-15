"""Ordering SQLAlchemy models."""

from sqlalchemy import JSON, Date, ForeignKey, Numeric, String, Text, Time, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, BaseModelMixin


class OrderModel(BaseModelMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.legacy_id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="PENDING")

    # Elite4Print financial fields
    total_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total_shipping_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    final_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    payment_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    extra_payment: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    is_additional_payment_paid: Mapped[bool] = mapped_column(default=False)
    original_total_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    original_shipping_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    original_tax_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    points_used: Mapped[int] = mapped_column(default=0)
    total_adjustment_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total_refunded_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    order_ref: Mapped[dict | None] = mapped_column(JSON, default=dict)

    jobs: Mapped[list[JobModel]] = relationship(
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

    # Elite4Print production fields
    job_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    group_id: Mapped[str] = mapped_column(String(40), default="")
    process_status: Mapped[str | None] = mapped_column(String(5), nullable=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paper: Mapped[str] = mapped_column(String(150), default="No Paper")
    size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quantity: Mapped[int] = mapped_column(default=0)
    coating: Mapped[str] = mapped_column(String(150), default="No Coating")
    color: Mapped[str] = mapped_column(String(150), default="No Color")
    trim_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    original_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    turnaround: Mapped[str] = mapped_column(String(50), default="2 Business days")
    turnaround_day: Mapped[int] = mapped_column(default=0)
    due_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    cut_off_time: Mapped[str] = mapped_column(Time, default="18:00:00")
    shipping_editable: Mapped[bool] = mapped_column(default=True)
    pickup_location: Mapped[str | None] = mapped_column(String(50), nullable=True)

    order: Mapped[OrderModel] = relationship("OrderModel", back_populates="jobs")
    memos: Mapped[list[JobMemoModel]] = relationship(
        "JobMemoModel",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class JobMemoModel(BaseModelMixin, Base):
    """Adjustment memo attached to a production job."""

    __tablename__ = "job_memos"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    note: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(10), default="PENDING")
    printing_adjustment: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    shipping_adjustment: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    adjustment_type: Mapped[str] = mapped_column(String(15), default="NONE")
    total_adjustment: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    job: Mapped[JobModel] = relationship("JobModel", back_populates="memos")
