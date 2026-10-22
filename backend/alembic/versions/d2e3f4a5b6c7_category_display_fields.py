"""Category display fields: image_url, is_active, sort_order.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-10-14

- image_url: optional thumbnail shown in the admin tree + storefront.
- is_active: soft visibility switch (inactive categories hide from the
  storefront but keep their products; the admin still lists them).
- sort_order: manual ordering (admin list sorts by it, then name).
- Rollback: `alembic downgrade -1` drops exactly these three columns.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('categories', sa.Column('image_url', sa.String(length=1000), nullable=True))
    op.add_column('categories', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('categories', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('categories', 'sort_order')
    op.drop_column('categories', 'is_active')
    op.drop_column('categories', 'image_url')
