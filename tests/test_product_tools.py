"""Tests for product lookup tool (mock/memory mode)."""
import os
import sys
from unittest.mock import MagicMock

os.environ["SESSION_BACKEND"] = "memory"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tools.product_tools import lookup_product, MOCK_PRODUCTS


def _ctx():
    ctx = MagicMock()
    ctx.state = {}
    return ctx


def test_lookup_product_found_by_keyword():
    result = lookup_product("headphones", _ctx())
    assert result["found"] is True
    assert len(result.get("products", [])) >= 1


def test_lookup_product_found_by_category():
    result = lookup_product("keyboard", _ctx())
    assert result["found"] is True


def test_lookup_product_not_found():
    result = lookup_product("flying car", _ctx())
    assert result["found"] is False


def test_lookup_product_empty_query():
    result = lookup_product("", _ctx())
    assert result["found"] is False
    assert "error" in result


def test_lookup_product_case_insensitive():
    result_lower = lookup_product("headphones", _ctx())
    result_upper = lookup_product("HEADPHONES", _ctx())
    assert result_lower["found"] == result_upper["found"]


def test_lookup_product_writes_session_state():
    ctx = _ctx()
    lookup_product("headphones", ctx)
    # Must write at least one state key
    assert ctx.state, "Expected session state to be written after product lookup"


def test_lookup_product_result_has_price():
    result = lookup_product("headphones", _ctx())
    assert result["found"] is True
    product = result["products"][0]
    assert "price_usd" in product
    assert isinstance(product["price_usd"], (int, float))


def test_lookup_product_result_has_stock():
    result = lookup_product("headphones", _ctx())
    product = result["products"][0]
    assert "stock_qty" in product


def test_mock_products_has_expected_categories():
    categories = {p["category"] for p in MOCK_PRODUCTS}
    assert "Audio" in categories
    assert "Television" in categories or "Peripherals" in categories
