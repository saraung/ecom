import importlib.util
from pathlib import Path
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.models.product_return import ReturnReason, ReturnRequest

NEW = {"return_requests", "return_items", "return_evidence", "return_events"}
FIELDS = {"return_request_id", "manual_transfer_reference"}
CLOUDINARY_FIELDS = {"secure_url", "cloudinary_public_id", "cloudinary_type"}


def feature_only(obj, name, kind, reflected, compare_to):
    if kind == "column" and name in CLOUDINARY_FIELDS:
        return False
    if kind == "index" and "cloudinary_public_id" in name:
        return False
    if kind == "table":
        return name in NEW or name == "refunds"
    if obj.table.name in NEW:
        return True
    if kind == "column":
        return name in FIELDS or name in CLOUDINARY_FIELDS
    return bool(set(obj.columns.keys()) & FIELDS)


def migration(filename="v7d8e9f0a1b2_product_returns.py"):
    path = Path(__file__).resolve().parents[1] / "alembic/versions" / filename
    spec = importlib.util.spec_from_file_location("product_return_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def legacy_schema():
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    orders = sa.Table("orders", metadata, sa.Column("id", sa.Uuid(), primary_key=True),
                      sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id")))
    items = sa.Table("order_items", metadata, sa.Column("id", sa.Uuid(), primary_key=True),
                     sa.Column("order_id", sa.Uuid(), sa.ForeignKey("orders.id")))
    refunds = sa.Table("refunds", metadata, sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), sa.ForeignKey("orders.id")), sa.Column("amount", sa.Numeric(12, 2)),
        sa.Column("idempotency_key", sa.String(100), unique=True), sa.Column("provider_refund_id", sa.String(100)))
    metadata.create_all(engine)
    user_id, order_id, refund_id = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(sa.insert(users).values(id=user_id))
        connection.execute(sa.insert(orders).values(id=order_id, user_id=user_id))
        connection.execute(sa.insert(items).values(id=uuid4(), order_id=order_id))
        connection.execute(sa.insert(refunds).values(id=refund_id, order_id=order_id, amount=25,
            idempotency_key="original-cancellation", provider_refund_id="original-provider-refund"))
    yield engine, metadata, user_id, order_id, refund_id
    engine.dispose()


def test_upgrade_is_additive_and_feature_schema_matches_models(legacy_schema):
    engine, metadata, user_id, order_id, refund_id = legacy_schema
    module = migration()
    with engine.begin() as connection:
        before = connection.execute(sa.select(metadata.tables["refunds"])).all()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert connection.execute(sa.select(metadata.tables["refunds"])).all() == before
        assert connection.execute(sa.text("SELECT return_request_id,manual_transfer_reference FROM refunds")).one() == (None, None)
        reverse = migration("w8e9f0a1b2c3_return_shipments.py")
        reverse.op = module.op
        reverse.upgrade()
        pickup = migration("x9f0a1b2c3d4_return_pickup_checkpoint.py")
        pickup.op = module.op
        pickup.upgrade()
        inspector = sa.inspect(connection)
        assert NEW <= set(inspector.get_table_names())
        for table, parent in (("return_requests", "orders"), ("return_items", "order_items"),
                              ("return_evidence", "return_requests"), ("return_events", "return_requests"), ("refunds", "return_requests")):
            assert any(fk["referred_table"] == parent for fk in inspector.get_foreign_keys(table))
        context = MigrationContext.configure(connection, opts={"include_object": feature_only})
        assert compare_metadata(context, SQLModel.metadata) == []
        request = ReturnRequest(order_id=order_id, user_id=user_id, idempotency_key=str(uuid4()), payload_hash="a" * 64,
                                reason=ReturnReason.DAMAGED, refund_amount=Decimal("10"))
        connection.execute(sa.insert(ReturnRequest.__table__).values(**request.model_dump()))
        assert connection.execute(sa.select(ReturnRequest.__table__)).first()


def test_constraints_reject_duplicate_owner_keys_and_invalid_states_quantities(legacy_schema):
    engine, _, user_id, order_id, _ = legacy_schema
    with engine.begin() as connection:
        module = migration()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        row = ReturnRequest(order_id=order_id, user_id=user_id, idempotency_key="same-key", payload_hash="a" * 64,
                            reason=ReturnReason.DAMAGED, refund_amount=Decimal("10"))
        reverse = migration("w8e9f0a1b2c3_return_shipments.py")
        reverse.op = module.op
        reverse.upgrade()
        pickup = migration("x9f0a1b2c3d4_return_pickup_checkpoint.py")
        pickup.op = module.op
        pickup.upgrade()
        connection.execute(sa.insert(ReturnRequest.__table__).values(**row.model_dump()))
        for updates in ({"id": uuid4()}, {"id": uuid4(), "idempotency_key": "new-key", "status": "invalid"},
                        {"id": uuid4(), "idempotency_key": "new-key", "refund_amount": -1}):
            with pytest.raises(sa.exc.IntegrityError):
                with connection.begin_nested():
                    connection.execute(sa.insert(ReturnRequest.__table__).values(**{**row.model_dump(), **updates}))
        with pytest.raises(sa.exc.IntegrityError):
            with connection.begin_nested():
                connection.execute(sa.text("INSERT INTO return_items(id,return_id,order_item_id,quantity,amount) "
                    "VALUES (:id,:return_id,:item_id,0,10)"),
                    {"id": uuid4().hex, "return_id": row.id.hex, "item_id": uuid4().hex})


def test_downgrade_removes_only_feature_schema_and_preserves_original_refund(legacy_schema):
    engine, metadata, *_ = legacy_schema
    with engine.begin() as connection:
        before = connection.execute(sa.select(metadata.tables["refunds"])).all()
        module = migration()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        module.downgrade()
        assert not NEW.intersection(sa.inspect(connection).get_table_names())
        assert connection.execute(sa.select(metadata.tables["refunds"])).all() == before
        assert not FIELDS.intersection(column["name"] for column in sa.inspect(connection).get_columns("refunds"))


def test_reverse_upgrade_and_downgrade_preserve_existing_return_and_forward_data(legacy_schema):
    engine, metadata, user_id, order_id, _ = legacy_schema
    reverse = migration("w8e9f0a1b2c3_return_shipments.py")
    pickup = migration("x9f0a1b2c3d4_return_pickup_checkpoint.py")
    with engine.begin() as connection:
        original = migration()
        original.op = reverse.op = pickup.op = Operations(MigrationContext.configure(connection))
        original.upgrade()
        request = ReturnRequest(order_id=order_id, user_id=user_id, idempotency_key=str(uuid4()), payload_hash="a" * 64,
                                reason=ReturnReason.DAMAGED, refund_amount=Decimal("10"), tracking_number="MANUAL-RETURN")
        fields = {"shiprocket_order_id", "shiprocket_shipment_id", "shipping_reference", "shipping_requested_at", "pickup_requested_at"}
        old_table = sa.Table("return_requests", sa.MetaData(), autoload_with=connection)
        values = {key: value.hex if isinstance(value, UUID) else value for key, value in request.model_dump(exclude=fields).items()}
        connection.execute(sa.insert(old_table).values(**values))
        before = connection.execute(sa.select(old_table)).all()
        forward = connection.execute(sa.select(metadata.tables["orders"])).all()
        reverse.upgrade()
        pickup.upgrade()
        assert connection.execute(sa.select(old_table)).all() == before
        assert connection.execute(sa.text("SELECT shiprocket_order_id,shiprocket_shipment_id,shipping_reference,shipping_requested_at,pickup_requested_at FROM return_requests")).one() == (None, None, None, None, None)
        assert all(column["nullable"] for column in sa.inspect(connection).get_columns("return_requests") if column["name"] in fields)
        indexes = sa.inspect(connection).get_indexes("return_requests")
        assert all(any(index["column_names"] == [name] and index["unique"] for index in indexes) for name in fields - {"shipping_requested_at", "pickup_requested_at"})
        pickup.downgrade()
        reverse.downgrade()
        assert connection.execute(sa.select(old_table)).all() == before
        assert connection.execute(sa.select(metadata.tables["orders"])).all() == forward
        assert not fields.intersection(column["name"] for column in sa.inspect(connection).get_columns("return_requests"))
