"""Add automatic coupons (coupon_type + trigger fields)

Revision ID: b4e8c2a91d73
Revises: 2f9c14a8b1e0
Create Date: 2026-09-15 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b4e8c2a91d73'
down_revision: Union[str, Sequence[str], None] = '2f9c14a8b1e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum types follow the existing 'discounttype' pattern (values stored as
# member NAMES, e.g. 'MANUAL' / 'MIN_CART_VALUE').
COUPON_TYPE = sa.Enum('MANUAL', 'AUTOMATIC', name='coupontype')
TRIGGER_TYPE = sa.Enum(
    'NONE',
    'MIN_CART_VALUE',
    'MIN_ITEM_COUNT',
    'CATEGORY_SPEND',
    'FIRST_ORDER',
    name='triggertype',
)


def upgrade() -> None:
    """Upgrade schema."""
    # Native enum types must exist before ADD COLUMN references them.
    COUPON_TYPE.create(op.get_bind(), checkfirst=True)
    TRIGGER_TYPE.create(op.get_bind(), checkfirst=True)
    
    # Existing rows become MANUAL coupons with no trigger — the current
    # manual flow keeps working untouched.
    op.add_column(
        'coupons',
        sa.Column('coupon_type', COUPON_TYPE, nullable=False, server_default='MANUAL'),
    )
    op.add_column(
        'coupons',
        sa.Column('trigger_type', TRIGGER_TYPE, nullable=False, server_default='NONE'),
    )
    op.add_column(
        'coupons',
        sa.Column('trigger_min_cart_value', sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        'coupons',
        sa.Column('trigger_min_item_count', sa.Integer(), nullable=True),
    )
    op.add_column(
        'coupons',
        sa.Column('trigger_category_id', sa.Uuid(), nullable=True),
    )
    op.add_column(
        'coupons',
        sa.Column('trigger_category_spend', sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.create_foreign_key(
        'fk_coupons_trigger_category_id_categories',
        'coupons',
        'categories',
        ['trigger_category_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'fk_coupons_trigger_category_id_categories',
        'coupons',
        type_='foreignkey',
    )
    op.drop_column('coupons', 'trigger_category_spend')
    op.drop_column('coupons', 'trigger_category_id')
    op.drop_column('coupons', 'trigger_min_item_count')
    op.drop_column('coupons', 'trigger_min_cart_value')
    op.drop_column('coupons', 'trigger_type')
    op.drop_column('coupons', 'coupon_type')
    TRIGGER_TYPE.drop(op.get_bind(), checkfirst=True)
    COUPON_TYPE.drop(op.get_bind(), checkfirst=True)
