"""Safe hard delete: order history blocks, dependents are cleaned up."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.models.cart import CartItem
from app.models.order import OrderItem
from app.models.product import Product, ProductVariant
from app.models.product_image import ProductImage
from app.models.review import Review
from app.models.review_image import ReviewImage
from app.models.wishlist import Wishlist
from app.repositories.product import bulk_delete_products


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def make_product(s, name="Widget", with_variant=True):
    p = Product(name=name, slug=name.lower().replace(" ", "-"), price=Decimal("10"))
    s.add(p)
    s.flush()
    variant = None
    if with_variant:
        variant = ProductVariant(product_id=p.id, sku=f"SKU-{uuid4().hex[:8]}", stock=5)
        s.add(variant)
        s.flush()
    s.add(ProductImage(product_id=p.id, url="https://example.com/i.png",
                       secure_url="https://example.com/i.png", cloudinary_public_id=f"pid-{p.id}"))
    s.flush()
    return p, variant


def test_hard_delete_removes_product_and_dependents(session):
    p, variant = make_product(session)
    review = Review(product_id=p.id, user_id=uuid4(), rating=5, title="Great")
    session.add(review)
    session.flush()
    session.add(ReviewImage(review_id=review.id, secure_url="https://example.com/r.png",
                            cloudinary_public_id="rid-1", filename="r.png"))
    session.add(Wishlist(user_id=uuid4(), product_id=p.id))
    session.add(CartItem(cart_id=uuid4(), variant_id=variant.id, quantity=1,
                         price_at_add=Decimal("10")))
    session.commit()

    result = bulk_delete_products(session, [p.id])

    assert result["deleted"] == [str(p.id)]
    assert result["blocked"] == []
    assert sorted(result["cloudinary_public_ids"]) == sorted([f"pid-{p.id}", "rid-1"])
    assert result["rag_product_ids"] == [str(p.id)]
    assert session.get(Product, p.id) is None
    assert session.exec(select(ProductVariant)).all() == []
    assert session.exec(select(ProductImage)).all() == []
    assert session.exec(select(Review)).all() == []
    assert session.exec(select(ReviewImage)).all() == []
    assert session.exec(select(Wishlist)).all() == []
    assert session.exec(select(CartItem)).all() == []


def test_order_history_blocks_hard_delete(session):
    p, variant = make_product(session)
    session.add(OrderItem(order_id=uuid4(), variant_id=variant.id, product_name=p.name,
                          variant_sku=variant.sku, quantity=1,
                          unit_price=Decimal("10"), line_total=Decimal("10")))
    session.commit()

    result = bulk_delete_products(session, [p.id])

    assert result["deleted"] == []
    assert len(result["blocked"]) == 1
    assert result["blocked"][0]["reason"] == "has order history"
    # Product untouched (soft-delete path still available via deactivate).
    assert session.get(Product, p.id) is not None
    assert session.get(Product, p.id).is_active is True


def test_partial_success_reports_blocked(session):
    clean, _ = make_product(session, name="Clean")
    ordered, ovar = make_product(session, name="Ordered")
    session.add(OrderItem(order_id=uuid4(), variant_id=ovar.id, product_name=ordered.name,
                          variant_sku=ovar.sku, quantity=1,
                          unit_price=Decimal("10"), line_total=Decimal("10")))
    session.commit()

    result = bulk_delete_products(session, [clean.id, ordered.id])

    assert result["deleted"] == [str(clean.id)]
    assert [b["name"] for b in result["blocked"]] == ["Ordered"]
    assert session.get(Product, clean.id) is None
    assert session.get(Product, ordered.id) is not None
