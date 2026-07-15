"""Add Elite4Print order/payment/product/coupon slice

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # User legacy UUID mapping
    # ------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column("legacy_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_users_legacy_id", "users", ["legacy_id"], unique=True)

    # orders.user_id was created as Integer in 0007; switch it to UUID so we can
    # preserve the Elite4Print user UUIDs from the real dump.
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_column("orders", "user_id")
    op.add_column(
        "orders",
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_orders_user_id",
        "orders",
        "users",
        ["user_id"],
        ["legacy_id"],
        ondelete="RESTRICT",
    )

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------
    op.create_table(
        "product_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("product_id", sa.String(length=255), nullable=False),
        sa.Column("created_by_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("product_type", sa.String(length=255), nullable=False, server_default="OFFSET"),
        sa.Column("min_price", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
        sa.Column("max_price", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
        sa.Column("sqr_ft_price", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
        sa.Column("shop_rate_per_hr", sa.Numeric(precision=8, scale=4), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("on_draft", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("base_turnaround", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("combined_shipping", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ordering", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("show_faq", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("shipping_type", sa.String(length=10), nullable=False, server_default="DEFAULT"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["product_categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.legacy_id"], ondelete="RESTRICT", name="fk_products_created_by_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index("ix_products_category_id", "products", ["category_id"], unique=False)
    op.create_index("ix_products_created_by_id", "products", ["created_by_id"], unique=False)
    op.create_index("ix_products_product_id", "products", ["product_id"], unique=True)

    # ------------------------------------------------------------------
    # Ordering extensions
    # ------------------------------------------------------------------
    op.add_column(
        "orders",
        sa.Column("total_price", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("total_shipping_price", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("final_price", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("discount_amount", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("payment_status", sa.String(length=32), nullable=False, server_default="PENDING"),
    )
    op.add_column(
        "orders",
        sa.Column("extra_payment", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("tax_amount", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("is_additional_payment_paid", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "orders",
        sa.Column("original_total_price", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("original_shipping_price", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("original_tax_amount", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("points_used", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("total_adjustment_amount", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("total_refunded_amount", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("order_ref", sa.JSON(), nullable=True),
    )

    op.add_column(
        "jobs",
        sa.Column("job_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("group_id", sa.String(length=40), nullable=False, server_default=""),
    )
    op.add_column(
        "jobs",
        sa.Column("process_status", sa.String(length=5), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("product_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("item_code", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("paper", sa.String(length=150), nullable=False, server_default="No Paper"),
    )
    op.add_column(
        "jobs",
        sa.Column("size", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "jobs",
        sa.Column("coating", sa.String(length=150), nullable=False, server_default="No Coating"),
    )
    op.add_column(
        "jobs",
        sa.Column("color", sa.String(length=150), nullable=False, server_default="No Color"),
    )
    op.add_column(
        "jobs",
        sa.Column("trim_size", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "jobs",
        sa.Column("original_price", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "jobs",
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("admin_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("turnaround", sa.String(length=50), nullable=False, server_default="2 Business days"),
    )
    op.add_column(
        "jobs",
        sa.Column("turnaround_day", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "jobs",
        sa.Column("due_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("cut_off_time", sa.Time(), nullable=False, server_default="18:00:00"),
    )
    op.add_column(
        "jobs",
        sa.Column("shipping_editable", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "jobs",
        sa.Column("pickup_location", sa.String(length=50), nullable=True),
    )
    op.create_index("ix_jobs_product_id", "jobs", ["product_id"], unique=False)
    op.create_foreign_key(
        "fk_jobs_product_id",
        "jobs",
        "products",
        ["product_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "job_memos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="PENDING"),
        sa.Column("printing_adjustment", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
        sa.Column("shipping_adjustment", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
        sa.Column("adjustment_type", sa.String(length=15), nullable=False, server_default="NONE"),
        sa.Column("total_adjustment", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_memos_job_id", "job_memos", ["job_id"], unique=False)

    # ------------------------------------------------------------------
    # Payment
    # ------------------------------------------------------------------
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="SUCCESS"),
        sa.Column("method", sa.String(length=10), nullable=False, server_default="CARD"),
        sa.Column("type", sa.String(length=10), nullable=False, server_default="PAYMENT"),
        sa.Column("trans_id", sa.String(length=255), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("card_number", sa.String(length=50), nullable=True),
        sa.Column("job_change_id", sa.Integer(), nullable=True),
        sa.Column("transactions_history", sa.JSON(), nullable=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_change_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.legacy_id"], ondelete="SET NULL", name="fk_payments_user_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_job_change_id", "payments", ["job_change_id"], unique=False)
    op.create_index("ix_payments_order_id", "payments", ["order_id"], unique=False)
    op.create_index("ix_payments_user_id", "payments", ["user_id"], unique=False)

    op.create_table(
        "pending_refunds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("card_number", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("transaction_id", sa.String(length=255), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pending_refunds_order_id", "pending_refunds", ["order_id"], unique=False)
    op.create_index("ix_pending_refunds_payment_id", "pending_refunds", ["payment_id"], unique=False)

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------
    op.create_table(
        "coupons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coupon_code", sa.String(length=50), nullable=False),
        sa.Column("coupon_on", sa.String(length=50), nullable=False),
        sa.Column("coupon_type", sa.String(length=50), nullable=False),
        sa.Column("coupon_value", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("max_discount", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
        sa.Column("coupon_start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coupon_expiry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limit_per_user", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("limit_per_coupon", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("coupon_description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coupon_code"),
    )
    op.create_index("ix_coupons_coupon_code", "coupons", ["coupon_code"], unique=True)

    op.create_table(
        "coupon_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coupon_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["coupon_id"], ["coupons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coupon_id", "product_id"),
    )
    op.create_index("ix_coupon_products_coupon_id", "coupon_products", ["coupon_id"], unique=False)
    op.create_index("ix_coupon_products_product_id", "coupon_products", ["product_id"], unique=False)

    op.create_table(
        "coupon_usages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coupon_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="RESERVED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["coupon_id"], ["coupons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.legacy_id"], ondelete="RESTRICT", name="fk_coupon_usages_user_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_coupon_usages_coupon_id", "coupon_usages", ["coupon_id"], unique=False)
    op.create_index("ix_coupon_usages_order_id", "coupon_usages", ["order_id"], unique=True)
    op.create_index("ix_coupon_usages_user_id", "coupon_usages", ["user_id"], unique=False)


def downgrade() -> None:
    # Drop FKs that reference users.legacy_id before removing the column.
    op.drop_constraint("fk_coupon_usages_user_id", "coupon_usages", type_="foreignkey")
    op.drop_constraint("fk_payments_user_id", "payments", type_="foreignkey")
    op.drop_constraint("fk_products_created_by_id", "products", type_="foreignkey")
    op.drop_constraint("fk_orders_user_id", "orders", type_="foreignkey")

    # Restore orders.user_id to Integer (matches 0007).
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_column("orders", "user_id")
    op.add_column(
        "orders",
        sa.Column("user_id", sa.Integer(), nullable=False),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"], unique=False)

    op.drop_index("ix_users_legacy_id", table_name="users")
    op.drop_column("users", "legacy_id")

    op.drop_index("ix_coupon_usages_user_id", table_name="coupon_usages")
    op.drop_index("ix_coupon_usages_order_id", table_name="coupon_usages")
    op.drop_index("ix_coupon_usages_coupon_id", table_name="coupon_usages")
    op.drop_table("coupon_usages")

    op.drop_index("ix_coupon_products_product_id", table_name="coupon_products")
    op.drop_index("ix_coupon_products_coupon_id", table_name="coupon_products")
    op.drop_table("coupon_products")

    op.drop_index("ix_coupons_coupon_code", table_name="coupons")
    op.drop_table("coupons")

    op.drop_index("ix_pending_refunds_payment_id", table_name="pending_refunds")
    op.drop_index("ix_pending_refunds_order_id", table_name="pending_refunds")
    op.drop_table("pending_refunds")

    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_index("ix_payments_job_change_id", table_name="payments")
    op.drop_table("payments")

    op.drop_index("ix_job_memos_job_id", table_name="job_memos")
    op.drop_table("job_memos")

    op.drop_constraint("fk_jobs_product_id", "jobs", type_="foreignkey")
    op.drop_index("ix_jobs_product_id", table_name="jobs")
    op.drop_column("jobs", "pickup_location")
    op.drop_column("jobs", "shipping_editable")
    op.drop_column("jobs", "cut_off_time")
    op.drop_column("jobs", "due_date")
    op.drop_column("jobs", "turnaround_day")
    op.drop_column("jobs", "turnaround")
    op.drop_column("jobs", "admin_notes")
    op.drop_column("jobs", "notes")
    op.drop_column("jobs", "original_price")
    op.drop_column("jobs", "price")
    op.drop_column("jobs", "trim_size")
    op.drop_column("jobs", "color")
    op.drop_column("jobs", "coating")
    op.drop_column("jobs", "quantity")
    op.drop_column("jobs", "size")
    op.drop_column("jobs", "paper")
    op.drop_column("jobs", "item_code")
    op.drop_column("jobs", "product_id")
    op.drop_column("jobs", "process_status")
    op.drop_column("jobs", "group_id")
    op.drop_column("jobs", "job_name")

    op.drop_column("orders", "order_ref")
    op.drop_column("orders", "total_refunded_amount")
    op.drop_column("orders", "total_adjustment_amount")
    op.drop_column("orders", "points_used")
    op.drop_column("orders", "original_tax_amount")
    op.drop_column("orders", "original_shipping_price")
    op.drop_column("orders", "original_total_price")
    op.drop_column("orders", "is_additional_payment_paid")
    op.drop_column("orders", "tax_amount")
    op.drop_column("orders", "extra_payment")
    op.drop_column("orders", "payment_status")
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "final_price")
    op.drop_column("orders", "total_shipping_price")
    op.drop_column("orders", "total_price")

    op.drop_index("ix_products_product_id", table_name="products")
    op.drop_index("ix_products_created_by_id", table_name="products")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_table("products")

    op.drop_table("product_categories")
