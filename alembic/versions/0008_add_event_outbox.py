"""Add event outbox, event store, dead letter, and idempotency tables

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_class_path", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_outbox_published_at_created_at",
        "event_outbox",
        ["published_at", "created_at"],
        unique=False,
    )

    op.create_table(
        "event_store",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("event_class_path", sa.String(length=255), nullable=False),
        sa.Column("aggregate_id", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_store_event_type", "event_store", ["event_type"], unique=False)
    op.create_index("ix_event_store_aggregate_id", "event_store", ["aggregate_id"], unique=False)
    op.create_index("ix_event_store_correlation_id", "event_store", ["correlation_id"], unique=False)
    op.create_index("ix_event_store_published_at", "event_store", ["published_at"], unique=False)

    op.create_table(
        "dead_letter_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_class_path", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "processed_events",
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_table("dead_letter_events")
    op.drop_index("ix_event_store_published_at", table_name="event_store")
    op.drop_index("ix_event_store_correlation_id", table_name="event_store")
    op.drop_index("ix_event_store_aggregate_id", table_name="event_store")
    op.drop_index("ix_event_store_event_type", table_name="event_store")
    op.drop_table("event_store")
    op.drop_index("ix_event_outbox_published_at_created_at", table_name="event_outbox")
    op.drop_table("event_outbox")
