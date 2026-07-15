"""Catalog SQLAlchemy models."""

from sqlalchemy import UUID, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, BaseModelMixin


class ProductCategoryModel(BaseModelMixin, Base):
    """Product category taxonomy."""

    __tablename__ = "product_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    products: Mapped[list[ProductModel]] = relationship(
        "ProductModel",
        back_populates="category",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProductModel(BaseModelMixin, Base):
    """Print product definition."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("product_categories.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.legacy_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    product_type: Mapped[str] = mapped_column(String(255), default="OFFSET")
    min_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    max_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    sqr_ft_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    shop_rate_per_hr: Mapped[float] = mapped_column(Numeric(8, 4), default=0)
    is_active: Mapped[bool] = mapped_column(default=False)
    on_draft: Mapped[bool] = mapped_column(default=True)
    base_turnaround: Mapped[int] = mapped_column(default=2)
    combined_shipping: Mapped[bool] = mapped_column(default=False)
    ordering: Mapped[int] = mapped_column(default=1)
    show_faq: Mapped[bool] = mapped_column(default=True)
    shipping_type: Mapped[str] = mapped_column(String(10), default="DEFAULT")

    category: Mapped[ProductCategoryModel] = relationship(
        "ProductCategoryModel", back_populates="products", lazy="selectin"
    )
