"""
Tests for review moderation (Phase A).

Covers:
  1. Hidden reviews are excluded from storefront list, average rating,
     and batch rating stats.
  2. Admin list sees hidden rows with product + reviewer identity,
     filters (rating/hidden/search) work.
  3. New reviews default to visible.

Run:  PYTHONPATH=. .venv/bin/python -m pytest tests/test_review_moderation.py -q
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlmodel import SQLModel, Session, create_engine

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.models.user import User, UserRole
from app.models.product import Product
from app.models.review import Review
from app.repositories import review as review_repo
from app.repositories import product as product_repo


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def seeded(session):
    user = User(
        username="buyer", email="buyer@t.com", full_name="Buyer",
        password_hash="x", role=UserRole.customer, is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    product = Product(name="Jacket", slug="jacket", price=Decimal("100.00"))
    session.add(product)
    session.commit()
    session.refresh(product)

    def _review(rating, title, hidden=False):
        r = Review(
            product_id=product.id, user_id=user.id, rating=rating,
            title=title, comment=f"{title} body", is_hidden=hidden,
        )
        session.add(r)
        session.commit()
        session.refresh(r)
        return r

    visible = _review(5, "Great jacket")
    spam = _review(1, "Spam abuse", hidden=True)
    return {"user": user, "product": product, "visible": visible, "spam": spam}


def test_1_hidden_excluded_from_storefront_list(session, seeded):
    rows = review_repo.get_reviews_by_product(session, seeded["product"].id)
    assert [r.title for r in rows] == ["Great jacket"]
    assert all(r.is_hidden is False for r in rows)


def test_2_hidden_excluded_from_averages(session, seeded):
    avg = review_repo.get_product_average_rating(session, seeded["product"].id)
    assert avg == 5.0, avg
    stats = product_repo.get_product_rating_stats(session, [seeded["product"].id])
    entry = stats[seeded["product"].id]
    assert entry == {"average_rating": 5.0, "review_count": 1}, entry


def test_3_admin_list_sees_everything_with_filters(session, seeded):
    rows, total = review_repo.list_reviews_admin(session)
    assert total == 2
    assert {r["title"] for r in rows} == {"Great jacket", "Spam abuse"}
    assert all(r["product_name"] == "Jacket" for r in rows)
    assert all(r["user_email"] == "buyer@t.com" for r in rows)

    hidden_rows, hidden_total = review_repo.list_reviews_admin(session, hidden=True)
    assert hidden_total == 1 and hidden_rows[0]["title"] == "Spam abuse"

    visible_rows, visible_total = review_repo.list_reviews_admin(session, hidden=False)
    assert visible_total == 1 and visible_rows[0]["title"] == "Great jacket"

    one_star, one_total = review_repo.list_reviews_admin(session, rating=1)
    assert one_total == 1 and one_star[0]["is_hidden"] is True

    found, found_total = review_repo.list_reviews_admin(session, search="jacket")
    assert found_total == 1 and found[0]["title"] == "Great jacket"


def test_4_new_reviews_default_visible(session, seeded):
    assert seeded["visible"].is_hidden is False
