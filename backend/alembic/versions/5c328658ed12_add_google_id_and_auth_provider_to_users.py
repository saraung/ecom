"""Add google_id and auth_provider to users

Revision ID: 5c328658ed12
Revises: 08defd8a8286
Create Date: 2026-08-21 12:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '5c328658ed12'
down_revision: Union[str, Sequence[str], None] = '08defd8a8286'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 👇 Step 1: Add auth_provider with default value first
    op.add_column('users', sa.Column('auth_provider', sa.String(), nullable=False, server_default='email'))
    
    # 👇 Step 2: Add google_id column (nullable initially)
    op.add_column('users', sa.Column('google_id', sa.String(), nullable=True))
    
    # 👇 Step 3: Create index for google_id
    op.create_index('ix_users_google_id', 'users', ['google_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_users_google_id', table_name='users')
    op.drop_column('users', 'google_id')
    op.drop_column('users', 'auth_provider')