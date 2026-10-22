from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.models.product import Product
from app.models.category import Category
from app.repositories.product import get_products, count_catalog_products
from app.api.v1.product import router
from app.db.database import get_session


@pytest.fixture
def catalog():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        parent = Category(name="Parent", slug="parent")
        s.add(parent)
        s.flush()
        child = Category(name="Child", slug="child", parent_id=parent.id)
        s.add(child)
        s.flush()
        for index in range(27):
            s.add(Product(id=UUID(int=index + 1), name="Same", slug=f"product-{index}",
                          description="Beyond twenty description" if index == 25 else "Ordinary",
                          price=Decimal("10"), is_active=index != 26,
                          category_id=child.id if index == 25 else None,
                          created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        s.commit()
        app = FastAPI()
        app.include_router(router)
        def session_dep():
            with Session(engine) as request_session:
                yield request_session
        app.dependency_overrides[get_session] = session_dep
        with TestClient(app) as client:
            yield s, client, parent.id, child.id
    engine.dispose()


@pytest.mark.parametrize("sort", ["newest", "oldest", "price_asc", "price_desc", "name_asc", "name_desc"])
def test_tied_sort_pages_have_no_duplicates_or_missing_products(catalog, sort):
    s, _, _, _ = catalog
    pages = [get_products(s, sort=sort, skip=offset, limit=10) for offset in (0, 10, 20)]
    ids = [product.id for page in pages for product in page]
    assert len(ids) == len(set(ids)) == 26
    assert ids == [UUID(int=index) for index in range(1, 27)]


def test_server_search_finds_description_beyond_initial_twenty(catalog):
    _, client, _, _ = catalog
    assert len(client.get("/products/").json()) == 20
    response = client.get("/products/", params={"search": "beyond twenty", "include_pagination": True})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["products"][0]["slug"] == "product-25"


def test_total_metadata_and_later_empty_page_preserve_list_contract(catalog):
    _, client, _, _ = catalog
    legacy = client.get("/products/", params={"page": 2}).json()
    assert isinstance(legacy, list) and len(legacy) == 6
    page = client.get("/products/", params={"include_pagination": True, "page": 3}).json()
    assert page == {"products": [], "total": 26, "page": 3, "limit": 20, "total_pages": 2}


def test_uuid_category_subtree_filter_and_count_agree(catalog):
    s, client, parent, child = catalog
    assert count_catalog_products(s, category_id=parent) == 0
    page = client.get("/products/", params={"category_id": str(parent), "include_descendants": True,
                                          "include_pagination": True}).json()
    assert page["total"] == 1 and page["products"][0]["category_id"] == str(child)


def test_search_wildcards_are_literal_and_inactive_detail_hidden(catalog):
    s, client, _, _ = catalog
    assert count_catalog_products(s, search="%") == 0
    assert count_catalog_products(s, search="_") == 0
    assert client.get("/products/product-26").status_code == 404


def test_invalid_page_bounds_and_price_range_rejected(catalog):
    _, client, _, _ = catalog
    for params in ({"page": 0}, {"limit": 101}, {"sort": "unsupported"}, {"category_id": "NaN"}):
        assert client.get("/products/", params=params).status_code == 422
    assert client.get("/products/", params={"min_price": 20, "max_price": 10}).status_code == 400
