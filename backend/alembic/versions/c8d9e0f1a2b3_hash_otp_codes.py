"""Store OTP codes hashed + drop pre-hash codes.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-09-28

OTP codes are now SHA-256 hex digests (64 chars). Old plaintext rows are
ephemeral 10-minute codes — purge the unused ones instead of migrating them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Invalidate every live plaintext code issued before hashing.
    op.execute(sa.text("DELETE FROM otps WHERE is_used = false"))
    op.alter_column(
        'otps', 'otp_code',
        existing_type=sa.String(length=6),
        type_=sa.String(length=128),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(sa.text("DELETE FROM otps WHERE is_used = false"))
    op.alter_column(
        'otps', 'otp_code',
        existing_type=sa.String(length=128),
        type_=sa.String(length=6),
        existing_nullable=False,
    )
