"""
Functional test for user order responses with product info.

Verifies that `OrderItemRead` (used by GET /orders, GET /orders/{id},
GET /orders/number/{num}) resolves for every order item:

  1. `product_id` + `product_slug` from item -> variant -> product
  2. `product_image` = the product's FIRST image (lowest sort_order)
  3. Missing variant/product (catalog row gone) -> fields are None, no crash
  4. The endpoint functions return objects that serialize with the new fields

Run:  PYTHONPATH=. python tests/test_order_product_info.py
"""
from decimal import Decimal
from uuid import uuid4

from sqlmodel import SQLModel, Session, create_engine

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.models.user import User, UserRole
from app.models.order import Order, OrderStatus, OrderItem
from app.models.address import Address
from app.models.product import Product, ProductVariant
from app.models.product_image import ProductImage

from app.repositories.order import (
    get_order_by_id,
    get_order_by_number,
    get_orders_by_user,
)
from app.api.v1.orders import get_order, get_orders
from app.schemas.order import OrderRead

ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

USER_ID = None
ORDER_ID = None
ORDER_NUMBER = "ORD-TEST-001"


def _seed():
    global USER_ID, ORDER_ID
    SQLModel.metadata.create_all(ENGINE)
    with Session(ENGINE) as s:
        user = User(
            username="customer", email="customer@test.com", full_name="John Doe",
            hashed_password="x", role=UserRole.customer, is_active=True,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        USER_ID = user.id

        addr = Address(
            user_id=user.id, label="Home", line1="1 Main St", city="Mumbai",
            state="MH", postal_code="400001", country="IN", is_default=True,
        )
        s.add(addr)
        s.commit()
        s.refresh(addr)

        product = Product(
            name="Classic Premium Cotton T-Shirt",
            slug="classic-premium-cotton-t-shirt",
            price=Decimal("749.00"),
        )
        s.add(product)
        s.commit()
        s.refresh(product)

        variant = ProductVariant(
            product_id=product.id, sku="TSHIRT-BLK-M",
            attributes={"size": "M", "color": "Black"}, stock=10,
        )
        s.add(variant)
        s.commit()
        s.refresh(variant)

        # Three images — the "first" image is the one with the LOWEST sort_order
        s.add(ProductImage(product_id=product.id, url="https://cdn/img-hero.jpg", sort_order=0))
        s.add(ProductImage(product_id=product.id, url="https://cdn/img-back.jpg", sort_order=5))
        s.add(ProductImage(product_id=product.id, url="https://cdn/img-alt.jpg", sort_order=2))

        order = Order(
            order_number=ORDER_NUMBER,
            user_id=user.id,
            shipping_address_id=addr.id,
            billing_address_id=addr.id,
            subtotal=Decimal("1498.00"),
            discount_total=Decimal("0"),
            tax_total=Decimal("269.64"),
            shipping_total=Decimal("0"),
            grand_total=Decimal("1767.64"),
            payment_method="online",
            payment_status="pending",
            status=OrderStatus.PENDING,
        )
        s.add(order)
        s.commit()
        s.refresh(order)
        ORDER_ID = order.id

        # Normal item
        s.add(OrderItem(
            order_id=order.id, variant_id=variant.id,
            product_name="Classic Premium Cotton T-Shirt",
            variant_sku=variant.sku,
            variant_attributes={"size": "M", "color": "Black"},
            quantity=2, unit_price=Decimal("749.00"), line_total=Decimal("1498.00"),
        ))
        # Item whose variant/product no longer exist in the catalog
        s.add(OrderItem(
            order_id=order.id, variant_id=uuid4(),
            product_name="Deleted Product",
            variant_sku="GONE-SKU",
            variant_attributes={},
            quantity=1, unit_price=Decimal("100.00"), line_total=Decimal("100.00"),
        ))
        s.commit()


def setup_module():
    if USER_ID is None:
        _seed()


def _find_real_item(items: list) -> dict:
    return next(i for i in items if i["variant_sku"] == "TSHIRT-BLK-M")


def test_order_items_have_product_info():
    with Session(ENGINE) as s:
        order = get_order_by_id(s, ORDER_ID)
        assert order is not None, "order not found"

        # This is exactly what FastAPI does for response_model=OrderRead
        payload = OrderRead.model_validate(order).model_dump(mode="json")

        assert payload["order_number"] == ORDER_NUMBER
        items = payload["items"]
        assert len(items) == 2

        real = _find_real_item(items)
        ghost = next(i for i in items if i["variant_sku"] == "GONE-SKU")

        # --- Real item: slug + first image (lowest sort_order) resolved ---
        assert real["product_slug"] == "classic-premium-cotton-t-shirt", real
        assert real["product_image"] == "https://cdn/img-hero.jpg", real
        assert real["product_id"] is not None
        # Snapshot fields unchanged
        assert real["product_name"] == "Classic Premium Cotton T-Shirt"
        assert real["quantity"] == 2
        assert real["unit_price"] == "749.00"
        assert real["variant_attributes"] == {"size": "M", "color": "Black"}

        # --- Ghost item: missing variant/product -> None, no crash ---
        assert ghost["product_slug"] is None, ghost
        assert ghost["product_image"] is None, ghost
        assert ghost["product_id"] is None


def test_user_orders_list_has_product_info():
    with Session(ENGINE) as s:
        orders = get_orders_by_user(s, USER_ID, skip=0, limit=20)
        assert len(orders) == 1
        payload = OrderRead.model_validate(orders[0]).model_dump(mode="json")
        real = _find_real_item(payload["items"])
        assert real["product_slug"] == "classic-premium-cotton-t-shirt"
        assert real["product_image"] == "https://cdn/img-hero.jpg"


def test_get_order_by_number_has_product_info():
    with Session(ENGINE) as s:
        order = get_order_by_number(s, ORDER_NUMBER)
        assert order is not None
        payload = OrderRead.model_validate(order).model_dump(mode="json")
        real = _find_real_item(payload["items"])
        assert real["product_slug"] == "classic-premium-cotton-t-shirt"
        assert real["product_image"] == "https://cdn/img-hero.jpg"


def test_endpoint_functions_serialize_with_product_info():
    """The actual endpoint handlers + response model produce the new fields."""
    with Session(ENGINE) as s:
        user = s.get(User, USER_ID)

        # GET /orders/{order_id}
        order = get_order(order_id=ORDER_ID, session=s, current_user=user)
        payload = OrderRead.model_validate(order).model_dump(mode="json")
        assert _find_real_item(payload["items"])["product_slug"] == \
            "classic-premium-cotton-t-shirt"

        # GET /orders (list)
        orders = get_orders(session=s, current_user=user, skip=0, limit=20)
        payloads = [OrderRead.model_validate(o).model_dump(mode="json") for o in orders]
        assert _find_real_item(payloads[0]["items"])["product_image"] == \
            "https://cdn/img-hero.jpg"


if __name__ == "__main__":
    _seed()
    test_order_items_have_product_info()
    print("✅ test_order_items_have_product_info passed")
    test_user_orders_list_has_product_info()
    print("✅ test_user_orders_list_has_product_info passed")
    test_get_order_by_number_has_product_info()
    print("✅ test_get_order_by_number_has_product_info passed")
    test_endpoint_functions_serialize_with_product_info()
    print("✅ test_endpoint_functions_serialize_with_product_info passed")
    print("\n🎉 All order product-info tests passed!")
