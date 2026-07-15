"""Promotion / coupon SQLAlchemy models."""

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, BaseModelMixin


class CouponModel(BaseModelMixin, Base):
    """Discount coupon definition."""

    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    coupon_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    coupon_on: Mapped[str] = mapped_column(String(50), nullable=False)
    coupon_type: Mapped[str] = mapped_column(String(50), nullable=False)
    coupon_value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    max_discount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    coupon_start_date: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    coupon_expiry_date: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    limit_per_user: Mapped[int] = mapped_column(default=-1)
    limit_per_coupon: Mapped[int] = mapped_column(default=-1)
    coupon_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    products: Mapped[list[CouponProductModel]] = relationship(
        "CouponProductModel",
        back_populates="coupon",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    usages: Mapped[list[CouponUsageModel]] = relationship(
        "CouponUsageModel",
        back_populates="coupon",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CouponProductModel(BaseModelMixin, Base):
    """Many-to-many link between coupons and products."""

    __tablename__ = "coupon_products"
    __table_args__ = (UniqueConstraint("coupon_id", "product_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    coupon_id: Mapped[int] = mapped_column(
        ForeignKey("coupons.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )

    coupon: Mapped[CouponModel] = relationship(
        "CouponModel", back_populates="products", lazy="selectin"
    )


class CouponUsageModel(BaseModelMixin, Base):
    """Reservation/confirmation of a coupon on an order."""

    __tablename__ = "coupon_usages"

    id: Mapped[int] = mapped_column(primary_key=True)
    coupon_id: Mapped[int] = mapped_column(
        ForeignKey("coupons.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.legacy_id", ondelete="RESTRICT"), index=True
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="RESERVED")

    coupon: Mapped[CouponModel] = relationship(
        "CouponModel", back_populates="usages", lazy="selectin"
    )
