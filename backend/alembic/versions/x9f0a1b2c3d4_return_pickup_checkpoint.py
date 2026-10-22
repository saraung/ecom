"""Durable checkpoint for reverse courier pickup requests."""
from alembic import op
import sqlalchemy as sa


revision = "x9f0a1b2c3d4"
down_revision = "w8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("return_requests", sa.Column("pickup_requested_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("return_requests", "pickup_requested_at")
