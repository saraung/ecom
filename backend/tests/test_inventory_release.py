from decimal import Decimal
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine

import app.models  # noqa: F401
from app.api.v1.orders import cancel_order
from app.api.v1.webhooks import process_tracking_event
from app.models.address import Address
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product, ProductVariant
from app.models.user import User
from app.schemas.order import CancelOrderRequest
from app.services.refund_service import restore_stock


def seed(engine):
    with Session(engine) as s:
        user = User(email="stock@example.com", username="stock")
        product = Product(name="Stock", slug="stock", price=Decimal("100"))
        s.add_all([user, product])
        s.flush()
        addr = Address(user_id=user.id, line1="Street", city="City", state="State", postal_code="12345", country="India")
        variant = ProductVariant(product_id=product.id, sku="stock", stock=3)
        s.add_all([addr, variant])
        s.flush()
        order = Order(order_number=str(uuid4()), user_id=user.id, shipping_address_id=addr.id,
                      billing_address_id=addr.id, subtotal=Decimal("200"), grand_total=Decimal("200"),
                      status=OrderStatus.CONFIRMED, payment_method="cod", payment_status="cod_pending", awb_code="stock_awb")
        s.add(order)
        s.flush()
        s.add(OrderItem(order_id=order.id, variant_id=variant.id, product_name="Stock", variant_sku="stock",
                        quantity=2, unit_price=Decimal("100"), line_total=Decimal("200")))
        s.commit()
        return user.id, order.id, variant.id


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    ids = seed(engine)
    yield engine, ids
    engine.dispose()


def test_duplicate_release_adds_stock_exactly_once(db):
    engine, (_, oid, vid) = db
    with Session(engine) as s:
        order = s.get(Order, oid)
        assert restore_stock(s, order) == 1
        assert restore_stock(s, order) == 0
        s.commit()
        assert s.get(ProductVariant, vid).stock == 5
        assert order.stock_released


def test_release_uses_atomic_increment_despite_stale_variant(db):
    engine, (_, oid, vid) = db
    with Session(engine) as stale:
        loaded = stale.get(ProductVariant, vid)
        with Session(engine) as writer:
            v = writer.get(ProductVariant, vid)
            v.stock = 8
            writer.add(v)
            writer.commit()
        restore_stock(stale, stale.get(Order, oid))
        stale.commit()
        assert loaded.stock == 10


def test_stale_order_cannot_be_cancelled_after_shipping(db):
    from fastapi import HTTPException
    engine, (uid, oid, vid) = db
    with Session(engine) as stale:
        loaded = stale.get(Order, oid)
        with Session(engine) as writer:
            order = writer.get(Order, oid)
            order.status = OrderStatus.SHIPPED
            writer.add(order)
            writer.commit()
        with pytest.raises(HTTPException) as exc:
            cancel_order(oid, CancelOrderRequest(reason="Cancel"), stale, stale.get(User, uid))
        assert exc.value.status_code == 400
        assert loaded.status == OrderStatus.SHIPPED
        assert stale.get(ProductVariant, vid).stock == 3


def test_stale_status_update_cannot_reactivate_cancelled_order(db):
    from fastapi import HTTPException
    from app.api.v1.admin.orders import update_order_status_admin
    from app.schemas.order import OrderStatusUpdate
    engine, (uid, oid, _) = db
    with Session(engine) as stale:
        loaded = stale.get(Order, oid)
        with Session(engine) as writer:
            order = writer.get(Order, oid)
            order.status = OrderStatus.CANCELLED
            writer.add(order)
            writer.commit()
        with pytest.raises(HTTPException):
            update_order_status_admin(oid, OrderStatusUpdate(status=OrderStatus.PROCESSING), stale, stale.get(User, uid))
        assert loaded.status == OrderStatus.CANCELLED


def test_rto_delivered_retry_with_different_scan_releases_once(db):
    engine, (_, oid, vid) = db
    with Session(engine) as s:
        process_tracking_event(s, {"awb": "stock_awb", "current_status": "RTO INITIATED"})
        assert s.get(ProductVariant, vid).stock == 3
        for date in ("2026-01-01", "2026-01-02"):
            process_tracking_event(s, {"awb": "stock_awb", "current_status": "RTO DELIVERED", "date": date})
        assert s.get(ProductVariant, vid).stock == 5
        assert s.get(Order, oid).stock_released


def test_release_claim_rolls_back_with_failed_increment(db):
    engine, (_, oid, vid) = db
    def fail(connection, cursor, statement, params, context, executemany):
        if statement.startswith("UPDATE product_variants"):
            raise RuntimeError("inventory update failed")
    with Session(engine) as s:
        event.listen(engine, "before_cursor_execute", fail)
        try:
            with pytest.raises(RuntimeError):
                restore_stock(s, s.get(Order, oid))
        finally:
            event.remove(engine, "before_cursor_execute", fail)
        assert not s.get(Order, oid).stock_released
        assert s.get(ProductVariant, vid).stock == 3


def test_cancel_then_rto_retry_cannot_release_inventory_again(db):
    engine, (uid, oid, vid) = db
    with Session(engine) as s:
        cancel_order(oid, CancelOrderRequest(reason="Cancel"), s, s.get(User, uid))
        process_tracking_event(s, {"awb": "stock_awb", "current_status": "RTO DELIVERED"})
        assert s.get(ProductVariant, vid).stock == 5


def test_migration_backfills_old_terminal_release(db):
    engine, (_, oid, _) = db
    with Session(engine) as s:
        order = s.get(Order, oid)
        order.status = OrderStatus.CANCELLED
        s.add(order)
        s.commit()
    path = Path(__file__).resolve().parents[1] / "alembic/versions/s4a5b6c7d8e9_inventory_release_guard.py"
    spec = importlib.util.spec_from_file_location("stock_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE orders DROP COLUMN stock_released")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
    with Session(engine) as s:
        assert s.get(Order, oid).stock_released


def test_postgres_cancel_rto_race_releases_once(postgres_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    uid, oid, vid = seed(postgres_engine)
    barrier = Barrier(2)
    def release():
        with Session(postgres_engine) as s:
            stale = s.get(Order, oid)
            barrier.wait(timeout=10)
            result = restore_stock(s, stale)
            s.commit()
            return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(release) for _ in range(2)]
        assert sorted(call.result(timeout=15) for call in calls) == [0, 1]
    with Session(postgres_engine) as s:
        assert s.get(ProductVariant, vid).stock == 5
