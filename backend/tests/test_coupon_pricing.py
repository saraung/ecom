"""
Automatic coupon pricing engine tests.

Follows the existing DB-free test style of this project: schema
validation, pure logic and object fakes (no database required).
"""
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.coupon import Coupon, CouponType, DiscountType, TriggerType
from app.schemas.cart import CartRead
from app.schemas.coupon import CouponCreate
from app.services import pricing as pricing_service


# ---------------------------------------------------------------
# Fakes (only attributes the engine touches)
# ---------------------------------------------------------------

def make_coupon(**overrides):
    defaults = dict(
        code="AUTO-TEST01",
        coupon_type=CouponType.AUTOMATIC,
        discount_type=DiscountType.PERCENTAGE,
        value=Decimal("10"),
        trigger_type=TriggerType.MIN_CART_VALUE,
        trigger_min_cart_value=Decimal("2000"),
        is_active=True,
        # naive datetimes, matching what the DB column returns
        valid_from=datetime.now(),
        valid_until=datetime.now() + timedelta(days=30),
        created_by=uuid4(),
    )
    defaults.update(overrides)
    return Coupon(**defaults)


def make_cart(items=None, coupon_code=None):
    return SimpleNamespace(
        id=uuid4(),
        items=items or [],
        coupon_code=coupon_code,
    )


def make_item(unit_price, quantity, category_id=None):
    return SimpleNamespace(
        id=uuid4(),
        variant_id=uuid4(),
        created_at=datetime.now(),
        price_at_add=Decimal(str(unit_price)),
        quantity=quantity,
        variant=SimpleNamespace(
            sku="SKU-1",
            attributes={},
            product=SimpleNamespace(
                name="Product",
                slug="product",
                images=[],
                category_id=category_id,
            ),
        ),
    )


def make_user():
    return SimpleNamespace(id=uuid4())


# ---------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------

def test_automatic_coupon_requires_trigger():
    with pytest.raises(ValidationError):
        CouponCreate(coupon_type="automatic", value=Decimal("10"))


def test_min_cart_value_trigger_requires_payload():
    with pytest.raises(ValidationError):
        CouponCreate(
            coupon_type="automatic",
            trigger_type="min_cart_value",
            value=Decimal("10"),
        )


def test_min_item_count_trigger_requires_payload():
    with pytest.raises(ValidationError):
        CouponCreate(
            coupon_type="automatic",
            trigger_type="min_item_count",
            value=Decimal("10"),
        )


def test_category_spend_trigger_requires_category_and_spend():
    with pytest.raises(ValidationError):
        CouponCreate(
            coupon_type="automatic",
            trigger_type="category_spend",
            value=Decimal("10"),
            trigger_category_spend=Decimal("500"),
        )
    with pytest.raises(ValidationError):
        CouponCreate(
            coupon_type="automatic",
            trigger_type="category_spend",
            value=Decimal("10"),
            trigger_category_id="3fa85f64-5717-4562-b3fc-2c963f66afa6",
        )


def test_valid_automatic_coupon_passes_validation():
    coupon = CouponCreate(
        coupon_type="automatic",
        trigger_type="first_order",
        value=Decimal("10"),
    )
    assert coupon.trigger_type.value == "first_order"


def test_manual_coupon_requires_code():
    with pytest.raises(ValidationError):
        CouponCreate(value=Decimal("10"))


def test_manual_coupon_forces_trigger_fields_off():
    coupon = CouponCreate(
        code="SUMMER20",
        value=Decimal("10"),
        trigger_type="min_cart_value",  # stale payload
        trigger_min_cart_value=Decimal("500"),
    )
    assert coupon.coupon_type == CouponType.MANUAL
    assert coupon.trigger_type == TriggerType.NONE
    assert coupon.trigger_min_cart_value is None


def test_cart_read_has_automatic_coupon_field():
    assert "automatic_coupon" in CartRead.model_fields


# ---------------------------------------------------------------
# Trigger evaluation
# ---------------------------------------------------------------

def test_trigger_min_cart_value():
    coupon = make_coupon(trigger_min_cart_value=Decimal("2000"))
    cart = make_cart([make_item(1500, 1)])
    assert not pricing_service._trigger_satisfied(
        None, coupon, cart, Decimal("1500"), 1, make_user()
    )
    cart2 = make_cart([make_item(1500, 2)])
    assert pricing_service._trigger_satisfied(
        None, coupon, cart2, Decimal("3000"), 2, make_user()
    )


def test_trigger_min_item_count():
    coupon = make_coupon(
        trigger_type=TriggerType.MIN_ITEM_COUNT,
        trigger_min_item_count=3,
    )
    cart = make_cart([make_item(100, 2)])
    assert not pricing_service._trigger_satisfied(
        None, coupon, cart, Decimal("200"), 2, make_user()
    )
    assert pricing_service._trigger_satisfied(
        None, coupon, cart, Decimal("200"), 3, make_user()
    )


def test_trigger_category_spend():
    coupon = make_coupon(
        trigger_type=TriggerType.CATEGORY_SPEND,
        trigger_category_id="cat-1",
        trigger_category_spend=Decimal("1000"),
    )
    cart = make_cart([
        make_item(600, 1, category_id="cat-1"),
        make_item(900, 1, category_id="cat-2"),
    ])
    assert pricing_service._category_spend(cart, "cat-1") == Decimal("600")
    assert not pricing_service._trigger_satisfied(
        None, coupon, cart, Decimal("1500"), 2, make_user()
    )
    cart2 = make_cart([make_item(1200, 1, category_id="cat-1")])
    assert pricing_service._trigger_satisfied(
        None, coupon, cart2, Decimal("1200"), 1, make_user()
    )


def test_trigger_first_order(monkeypatch):
    coupon = make_coupon(trigger_type=TriggerType.FIRST_ORDER)
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_completed_order_count", lambda s, u: 0
    )
    assert pricing_service._trigger_satisfied(
        None, coupon, make_cart(), Decimal("100"), 1, make_user()
    )
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_completed_order_count", lambda s, u: 2
    )
    assert not pricing_service._trigger_satisfied(
        None, coupon, make_cart(), Decimal("100"), 1, make_user()
    )
    # guests never qualify for automatic coupons
    assert not pricing_service._trigger_satisfied(
        None, coupon, make_cart(), Decimal("100"), 1, None
    )


# ---------------------------------------------------------------
# Precedence: exactly one winner, manual always beats automatic
# ---------------------------------------------------------------

def test_manual_wins_over_automatic(monkeypatch):
    manual = make_coupon(
        code="SUMMER20",
        coupon_type=CouponType.MANUAL,
        trigger_type=TriggerType.NONE,
        discount_type=DiscountType.FIXED,
        value=Decimal("100"),
    )
    auto = make_coupon(value=Decimal("10"), trigger_min_cart_value=Decimal("0"))
    cart = make_cart([make_item(500, 2)], coupon_code="SUMMER20")

    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_coupon_by_code", lambda s, code: manual
    )
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_user_coupon_usage_count", lambda *a: 0
    )
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_active_automatic_coupons", lambda s: [auto]
    )

    pricing = pricing_service.resolve_cart_pricing(None, cart, make_user())
    assert pricing.manual is not None
    assert pricing.automatic is None
    assert pricing.discount_total == Decimal("100")
    assert pricing.new_subtotal == Decimal("900")


def test_automatic_applies_when_no_manual(monkeypatch):
    auto = make_coupon(value=Decimal("10"), trigger_min_cart_value=Decimal("100"))
    cart = make_cart([make_item(500, 2)])  # subtotal 1000

    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_user_coupon_usage_count", lambda *a: 0
    )
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_active_automatic_coupons", lambda s: [auto]
    )

    pricing = pricing_service.resolve_cart_pricing(None, cart, make_user())
    assert pricing.manual is None
    assert pricing.automatic is not None
    assert pricing.discount_total == Decimal("100")  # 10% of 1000
    # tax is computed on the POST-discount subtotal
    assert pricing.tax_total == Decimal("900") * pricing_service._tax_rate()
    assert pricing.total == (
        pricing.new_subtotal + pricing.tax_total + pricing.shipping_total
    )


def test_best_automatic_wins(monkeypatch):
    weaker = make_coupon(code="AUTO-WEAK", value=Decimal("5"), trigger_min_cart_value=Decimal("100"))
    stronger = make_coupon(code="AUTO-STRONG", value=Decimal("10"), trigger_min_cart_value=Decimal("100"))
    cart = make_cart([make_item(500, 2)])

    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_user_coupon_usage_count", lambda *a: 0
    )
    monkeypatch.setattr(
        pricing_service.coupon_repo,
        "get_active_automatic_coupons",
        lambda s: [weaker, stronger],
    )

    pricing = pricing_service.resolve_cart_pricing(None, cart, make_user())
    assert pricing.automatic.coupon.code == "AUTO-STRONG"


def test_ineligible_automatic_coupons_ignored(monkeypatch):
    inactive = make_coupon(code="AUTO-OFF", is_active=False)
    below = make_coupon(code="AUTO-LOW", trigger_min_cart_value=Decimal("99999"))
    cart = make_cart([make_item(500, 2)])

    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_user_coupon_usage_count", lambda *a: 0
    )
    monkeypatch.setattr(
        pricing_service.coupon_repo,
        "get_active_automatic_coupons",
        lambda s: [inactive, below],
    )

    pricing = pricing_service.resolve_cart_pricing(None, cart, make_user())
    assert pricing.automatic is None


def test_guests_get_no_automatic_coupon(monkeypatch):
    auto = make_coupon(trigger_min_cart_value=Decimal("0"))
    cart = make_cart([make_item(500, 2)])
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_active_automatic_coupons", lambda s: [auto]
    )
    pricing = pricing_service.resolve_cart_pricing(None, cart, None)
    assert pricing.automatic is None
    assert pricing.discount_total == Decimal("0")


def test_empty_cart_gets_no_automatic_coupon(monkeypatch):
    auto = make_coupon(trigger_type=TriggerType.FIRST_ORDER)
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_active_automatic_coupons", lambda s: [auto]
    )
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_completed_order_count", lambda s, u: 0
    )
    pricing = pricing_service.resolve_cart_pricing(None, make_cart(), make_user())
    assert pricing.automatic is None


def test_expired_manual_code_not_counted(monkeypatch):
    manual = make_coupon(
        code="OLD20",
        coupon_type=CouponType.MANUAL,
        trigger_type=TriggerType.NONE,
        valid_until=datetime.now() - timedelta(days=1),
    )
    cart = make_cart([make_item(500, 2)], coupon_code="OLD20")
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_coupon_by_code", lambda s, code: manual
    )
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_user_coupon_usage_count", lambda *a: 0
    )
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_active_automatic_coupons", lambda s: []
    )

    pricing = pricing_service.resolve_cart_pricing(None, cart, make_user())
    assert pricing.manual is None
    assert pricing.discount_total == Decimal("0")
    # the pill stays visible; the discount simply isn't counted
    assert pricing_service.build_cart_read(cart, pricing).coupon_code == "OLD20"


def test_trigger_description_strings():
    from app.core.region import format_money

    assert format_money(2000) in pricing_service.trigger_description(
        make_coupon(trigger_min_cart_value=Decimal("2000"))
    )
    assert "3+ items" in pricing_service.trigger_description(
        make_coupon(
            trigger_type=TriggerType.MIN_ITEM_COUNT,
            trigger_min_item_count=3,
        )
    )
    assert "first order" in pricing_service.trigger_description(
        make_coupon(trigger_type=TriggerType.FIRST_ORDER)
    )


def test_build_cart_read_includes_automatic_coupon(monkeypatch):
    auto = make_coupon(value=Decimal("10"), trigger_min_cart_value=Decimal("100"))
    cart = make_cart([make_item(500, 2)])

    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_user_coupon_usage_count", lambda *a: 0
    )
    monkeypatch.setattr(
        pricing_service.coupon_repo, "get_active_automatic_coupons", lambda s: [auto]
    )

    pricing = pricing_service.resolve_cart_pricing(None, cart, make_user())
    payload = pricing_service.build_cart_read(cart, pricing)
    assert payload.automatic_coupon is not None
    assert payload.automatic_coupon.code == "AUTO-TEST01"
    assert payload.automatic_coupon.discount_amount == Decimal("100")
    assert payload.automatic_coupon.description != ""
    assert payload.coupon_code is None
    assert payload.discount_total == Decimal("100")
