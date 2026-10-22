from decimal import Decimal
from pathlib import Path
import importlib.util
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

import app.models  # noqa: F401
from app.models.cart import Cart, CartItem, CartMergeReceipt
from app.models.product import Product, ProductVariant
from app.models.user import User
from app.repositories.cart import merge_cart_item


@pytest.fixture
def data():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        user = User(email="merge@example.com", username="merge", password_hash="x")
        product = Product(name="Merge", slug="merge", price=Decimal("100"))
        s.add_all([user, product])
        s.flush()
        cart = Cart(user_id=user.id)
        variant = ProductVariant(product_id=product.id, sku="merge", stock=10)
        s.add_all([cart, variant])
        s.commit()
        yield s, cart, variant
    engine.dispose()


def test_merge_retry_and_duplicate_variants_are_lossless(data):
    s, cart, variant = data
    key = uuid4()
    merge_cart_item(s, cart, variant.id, 2, key)
    merge_cart_item(s, cart, variant.id, 2, key)
    merge_cart_item(s, cart, variant.id, 3, uuid4())
    assert s.exec(select(CartItem)).one().quantity == 5
    assert len(s.exec(select(CartMergeReceipt)).all()) == 2


def test_conflicting_key_cannot_mutate_existing_cart(data):
    s, cart, variant = data
    key = uuid4()
    merge_cart_item(s, cart, variant.id, 2, key)
    with pytest.raises(ValueError, match="different cart entry"):
        merge_cart_item(s, cart, variant.id, 3, key)
    assert s.exec(select(CartItem)).one().quantity == 2


def test_merge_refreshes_item_loaded_before_another_writer(data):
    s, cart, variant = data
    merge_cart_item(s, cart, variant.id, 2, uuid4())
    stale = s.exec(select(CartItem)).one()
    with Session(s.get_bind()) as other:
        item = other.get(CartItem, stale.id)
        item.quantity = 6
        other.add(item)
        other.commit()
    merge_cart_item(s, cart, variant.id, 1, uuid4())
    assert s.exec(select(CartItem)).one().quantity == 7


def test_stock_conflict_does_not_record_receipt_and_can_be_retried(data):
    s, cart, variant = data
    key = uuid4()
    with pytest.raises(ValueError, match="available"):
        merge_cart_item(s, cart, variant.id, 11, key)
    assert s.exec(select(CartMergeReceipt)).all() == []
    assert s.exec(select(CartItem)).all() == []
    variant.stock = 11
    s.add(variant)
    s.commit()
    merge_cart_item(s, cart, variant.id, 11, key)
    assert s.exec(select(CartItem)).one().quantity == 11


def test_receipt_and_cart_roll_back_together(data):
    s, cart, variant = data
    def fail(session):
        raise RuntimeError("commit failed")
    event.listen(s, "before_commit", fail)
    with pytest.raises(RuntimeError):
        merge_cart_item(s, cart, variant.id, 2, uuid4())
    event.remove(s, "before_commit", fail)
    assert s.exec(select(CartItem)).all() == []
    assert s.exec(select(CartMergeReceipt)).all() == []


def test_receipt_migration_upgrade(data):
    s, cart, variant = data
    engine = s.get_bind()
    s.close()
    path = Path(__file__).resolve().parents[1] / "alembic/versions/p1d2e3f4a5b6_guest_cart_merge_receipts.py"
    spec = importlib.util.spec_from_file_location("merge_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE cart_merge_receipts")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
    assert "cart_merge_receipts" in __import__("sqlalchemy").inspect(engine).get_table_names()
