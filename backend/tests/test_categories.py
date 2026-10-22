from app.api.v1.categories import router
from app.schemas.category import CategoryCreate


def test_category_schema_and_router_registration():
    payload = CategoryCreate(name="Shoes", slug="shoes")

    assert payload.name == "Shoes"
    assert payload.slug == "shoes"
    assert any(route.path == router.prefix for route in router.routes)
    assert any(route.path == f"{router.prefix}/{{category_id}}" for route in router.routes)
