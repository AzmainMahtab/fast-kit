"""Add assignment audit to rbac junctions

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-30

"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # role_permissions audit columns
    op.add_column(
        "role_permissions",
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "role_permissions",
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # user_roles audit columns
    op.add_column(
        "user_roles",
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "user_roles",
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_roles", "assigned_at")
    op.drop_column("user_roles", "assigned_by")
    op.drop_column("role_permissions", "assigned_at")
    op.drop_column("role_permissions", "assigned_by")
