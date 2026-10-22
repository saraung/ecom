"""Scope refresh tokens per API audience (storefront vs admin).

Revision ID: b5d7f2a9c4e1
Revises: e8f9a0b1c2d3
Create Date: 2026-09-28

- refresh_tokens.scope: which API a session may talk to. Persisted so that
  POST /auth/refresh re-issues with the SAME audience instead of silently
  minting a full-privilege token for a storefront session.
- Existing rows default to 'admin': every refresh token issued before this
  migration came from the OTP-gated login, so 'admin' is the correct scope.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b5d7f2a9c4e1'
down_revision: Union[str, Sequence[str], None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'refresh_tokens',
        sa.Column(
            'scope',
            sa.String(length=20),
            nullable=False,
            server_default='admin',
        ),
    )
    op.create_index(
        'ix_refresh_tokens_scope', 'refresh_tokens', ['scope']
    )


def downgrade() -> None:
    op.drop_index('ix_refresh_tokens_scope', table_name='refresh_tokens')
    op.drop_column('refresh_tokens', 'scope')