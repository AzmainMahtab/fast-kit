"""uuid v7 server default

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-16

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


uuid_generate_v7_sql = """
CREATE OR REPLACE FUNCTION uuid_generate_v7() RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    unix_ts_ms bigint;
    ts_bytes bytea;
    rand_bytes bytea;
    uuid_bytes bytea;
BEGIN
    unix_ts_ms := (extract(epoch FROM clock_timestamp()) * 1000)::bigint;
    ts_bytes := substring(int8send(unix_ts_ms) from 1 for 6);
    rand_bytes := gen_random_bytes(10);
    uuid_bytes := ts_bytes || rand_bytes;
    uuid_bytes := set_byte(uuid_bytes, 6, (get_byte(uuid_bytes, 6) & 15) | 112);
    uuid_bytes := set_byte(uuid_bytes, 8, (get_byte(uuid_bytes, 8) & 63) | 128);
    RETURN encode(uuid_bytes, 'hex')::uuid;
END;
$$;
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(uuid_generate_v7_sql)
    op.execute("ALTER TABLE users ALTER COLUMN uuid SET DEFAULT uuid_generate_v7()")


def downgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN uuid SET DEFAULT gen_random_uuid()")
    op.execute("DROP FUNCTION IF EXISTS uuid_generate_v7()")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
