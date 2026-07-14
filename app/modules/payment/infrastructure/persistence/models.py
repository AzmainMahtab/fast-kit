"""Payment SQLAlchemy models."""

from sqlalchemy import JSON, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, BaseModelMixin


class PaymentModel(BaseModelMixin, Base):
    """Payment or refund transaction."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="SUCCESS")
    method: Mapped[str] = mapped_column(String(10), default="CARD")
    type: Mapped[str] = mapped_column(String(10), default="PAYMENT")
    trans_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    card_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    job_change_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    transactions_history: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    pending_refunds: Mapped[list[PendingRefundModel]] = relationship(
        "PendingRefundModel",
        back_populates="payment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PendingRefundModel(BaseModelMixin, Base):
    """Refund queued for asynchronous processing."""

    __tablename__ = "pending_refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    card_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    transaction_id: Mapped[str] = mapped_column(String(255), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)
    points: Mapped[int | None] = mapped_column(nullable=True)

    payment: Mapped[PaymentModel] = relationship(
        "PaymentModel",
        back_populates="pending_refunds",
        lazy="selectin",
    )
