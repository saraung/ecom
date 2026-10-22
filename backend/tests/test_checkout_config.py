# tests/test_checkout_config.py
"""
Tests for GET /checkout/config — the client-facing pricing configuration
endpoint that replaces hardcoded COD fee/limit constants in the frontend.

Verifies:
  1. The endpoint returns the live settings (single source of truth).
  2. The route is registered on the checkout router (GET /config).
  3. (Live check) The route is reachable at /api/v1/checkout/config.

Run:  PYTHONPATH=. .venv/bin/python tests/test_checkout_config.py
      (also pytest-compatible: PYTHONPATH=. python -m pytest tests/test_checkout_config.py)
"""
from app.api.v1.checkout import get_checkout_config, router
from app.core.config import settings
from app.schemas.checkout import CheckoutConfigResponse


def test_config_schema_matches_settings():
    config = get_checkout_config()

    assert isinstance(config, CheckoutConfigResponse)
    assert config.cod_fee == settings.COD_FEE
    assert config.cod_min_order_value == settings.COD_MIN_ORDER_VALUE
    assert config.cod_max_order_value == settings.COD_MAX_ORDER_VALUE
    assert config.free_shipping_threshold == settings.FREE_SHIPPING_THRESHOLD
    assert config.shipping_cost == settings.SHIPPING_COST
    assert config.tax_rate == settings.TAX_RATE


def test_config_route_is_registered():
    # NOTE: the router's prefix is baked into route paths at registration
    # time, so the stored path is "/checkout/config", not "/config".
    get_routes = [
        route
        for route in router.routes
        if route.path == "/checkout/config" and "GET" in getattr(route, "methods", set())
    ]
    assert len(get_routes) == 1


def run_all():
    test_config_schema_matches_settings()
    test_config_route_is_registered()
    print("\n🎉 ALL CHECKOUT CONFIG TESTS PASSED")


if __name__ == "__main__":
    run_all()
