"""Product cards for chat: helper mapping + endpoint passthrough."""
from app.api.v1.mcp import McpChatResponse
from app.mcp.agent import (
    MAX_PRODUCT_CARDS,
    _card_candidates,
    _to_product_card,
    collect_product_cards,
)


def _summary(**over):
    base = {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Demo Jacket",
        "slug": "demo-jacket",
        "price": "2499.00",
        "is_active": True,
        "image_url": "https://example.com/i.png",
    }
    base.update(over)
    return base


def test_to_product_card_whitelists():
    card = _to_product_card({**_summary(), "preview_token": "SECRET", "cost": 1}, stock="7")
    assert card["name"] == "Demo Jacket"
    assert card["stock"] == 7
    assert "preview_token" not in card and "cost" not in card


def test_to_product_card_rejects_idless():
    assert _to_product_card({"name": "No id"}) is None
    assert _to_product_card(None) is None


def test_candidates_get_product_sums_variant_stock():
    result = {
        "success": True,
        "product": {**_summary(), "variants": [{"stock": 3}, {"stock": 4}]},
    }
    pairs = _card_candidates("get_product", result)
    assert len(pairs) == 1
    card = _to_product_card(*pairs[0])
    assert card["stock"] == 7


def test_candidates_list_caps_at_max():
    result = {
        "success": True,
        "products": [_summary(id=f"id-{i}", name=f"P{i}") for i in range(9)],
    }
    assert len(_card_candidates("list_products", result)) == MAX_PRODUCT_CARDS


def test_candidates_analytics_normalizes_keys():
    result = {
        "success": True,
        "products": [
            {
                "product_id": "22222222-2222-2222-2222-222222222222",
                "product_name": "Top Seller",
                "product_slug": "top-seller",
                "average_price": 99.5,
                "total_quantity_sold": 13,
                "image_url": "https://example.com/t.png",
            }
        ],
    }
    pairs = _card_candidates("product_performance", result)
    assert len(pairs) == 1
    card = _to_product_card(*pairs[0])
    assert card["id"] == "22222222-2222-2222-2222-222222222222"
    assert card["name"] == "Top Seller"
    assert card["slug"] == "top-seller"
    assert card["image_url"] == "https://example.com/t.png"
    # Units sold must never masquerade as stock.
    assert card["stock"] is None


def test_candidates_rejects_failures_and_unknown_tools():
    assert _card_candidates("get_product", {"success": False}) == []
    assert _card_candidates("cancel_order", {"success": True}) == []
    assert _card_candidates("product_performance", {"success": True}) == []


def test_endpoint_passes_product_cards_through():
    cards = [_to_product_card(_summary())]
    res = McpChatResponse(reply="hi", tools_used=["get_product"], product_cards=cards)
    assert res.model_dump()["product_cards"] == cards
    # Back-compat: omitted when absent.
    assert McpChatResponse(reply="hi").model_dump()["product_cards"] == []


def test_collect_attaches_without_confirmation_flag():
    # Regression: collection once lived inside the requires_confirmation
    # branch, so read-only lookups (which never set it) attached nothing.
    cards, seen = [], set()
    collect_product_cards(
        "get_product",
        {"success": True, "product": _summary()},
        cards, seen,
    )
    assert len(cards) == 1 and cards[0]["name"] == "Demo Jacket"


def test_collect_dedupes_and_caps():
    cards, seen = [], set()
    for i in range(9):
        collect_product_cards(
            "list_products",
            {"success": True, "products": [_summary(id=f"id-{i}", name=f"P{i}")]},
            cards, seen,
        )
    assert len(cards) == MAX_PRODUCT_CARDS
    # Re-offering the same product never duplicates.
    collect_product_cards(
        "get_product", {"success": True, "product": _summary(id="id-0")},
        cards, seen,
    )
    assert len(cards) == MAX_PRODUCT_CARDS


def test_collect_ignores_non_card_tools():
    cards, seen = [], set()
    collect_product_cards(
        "cancel_order", {"success": True, "order": {"id": "x"}},
        cards, seen,
    )
    assert cards == []
