"""Track the Cloudinary asset behind a category thumbnail.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-14

- image_public_id lets re-uploads delete the previous Cloudinary asset
  instead of orphaning it (same discipline as product images).
- Rollback: `alembic downgrade -1` drops the column.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, Sequence[str], None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('categories', sa.Column('image_public_id', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('categories', 'image_public_id')
