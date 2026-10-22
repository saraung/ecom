"""Refresh families, user invalidation version and hashed reset tokens.

Revision ID: o0c1d2e3f4a5
Revises: n9b0c1d2e3f4
"""
import hashlib
from alembic import op
import sqlalchemy as sa

revision = "o0c1d2e3f4a5"
down_revision = "n9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("refresh_tokens", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE refresh_tokens SET session_id = id")
    # SQLite needs batch mode; production PostgreSQL can alter in place.
    with op.batch_alter_table("refresh_tokens") as batch:
        batch.alter_column("session_id", existing_type=sa.Uuid(), nullable=False)
        batch.create_index("ix_refresh_tokens_session_id", ["session_id"])
    resets = sa.Table("password_reset_tokens", sa.MetaData(), autoload_with=op.get_bind())
    for row in op.get_bind().execute(sa.select(resets.c.id, resets.c.token)).mappings():
        digest = hashlib.sha256(row["token"].encode()).hexdigest()
        op.get_bind().execute(resets.update().where(resets.c.id == row["id"]).values(token=digest))


def downgrade():
    # Hashing is intentionally irreversible; old reset links must be reissued.
    op.execute("DELETE FROM password_reset_tokens")
    op.drop_index("ix_refresh_tokens_session_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "session_id")
    op.drop_column("users", "token_version")
