"""Freeze customer/address details on orders.

Revision ID: n9b0c1d2e3f4
Revises: m8a9b0c1d2e3
"""
from alembic import op
import sqlalchemy as sa

revision = "n9b0c1d2e3f4"
down_revision = "m8a9b0c1d2e3"
branch_labels = None
depends_on = None


def backfill(connection):
    metadata = sa.MetaData()
    orders = sa.Table("orders", metadata, autoload_with=connection)
    users = sa.Table("users", metadata, autoload_with=connection)
    addresses = sa.Table("addresses", metadata, autoload_with=connection)
    for order in connection.execute(sa.select(orders)).mappings():
        user = connection.execute(sa.select(users).where(users.c.id == order["user_id"])).mappings().one()
        snapshots = {"customer_snapshot": {"id": str(user["id"]), **{
            key: user[key] for key in ("full_name", "username", "email", "phone")}}}
        for kind in ("shipping", "billing"):
            address = connection.execute(sa.select(addresses).where(
                addresses.c.id == order[f"{kind}_address_id"])).mappings().one()
            snapshots[f"{kind}_snapshot"] = {"id": str(address["id"]), **{
                key: address[key] for key in ("label", "line1", "line2", "city", "state", "postal_code", "country", "is_default")},
                "full_name": user["full_name"], "phone": user["phone"]}
        connection.execute(orders.update().where(orders.c.id == order["id"]).values(**snapshots))


def upgrade():
    for name in ("customer_snapshot", "shipping_snapshot", "billing_snapshot"):
        op.add_column("orders", sa.Column(name, sa.JSON(), nullable=True))
    backfill(op.get_bind())


def downgrade():
    # Downgrade discards historical copies; back up these columns beforehand.
    for name in ("billing_snapshot", "shipping_snapshot", "customer_snapshot"):
        op.drop_column("orders", name)
