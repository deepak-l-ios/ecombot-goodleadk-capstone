"""Tests for order tools (mock/memory mode)."""
import os
import sys
from unittest.mock import MagicMock

os.environ["SESSION_BACKEND"] = "memory"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tools.order_tools import get_order_status, cancel_order, save_customer_name, MOCK_ORDERS


def _ctx():
    ctx = MagicMock()
    ctx.state = {}
    return ctx


# get_order_status

def test_get_order_status_found():
    result = get_order_status("ORD-001", _ctx())
    assert result["found"] is True
    assert result["order_id"] == "ORD-001"
    assert "status" in result
    assert "carrier" in result


def test_get_order_status_not_found():
    result = get_order_status("ORD-999", _ctx())
    assert result["found"] is False


def test_get_order_status_invalid_format():
    result = get_order_status("INVALID", _ctx())
    assert result["found"] is False
    assert "error" in result


def test_get_order_status_empty_string():
    result = get_order_status("", _ctx())
    assert result["found"] is False
    assert "error" in result


def test_get_order_status_writes_current_order_id():
    ctx = _ctx()
    get_order_status("ORD-001", ctx)
    assert ctx.state.get("current_order_id") == "ORD-001"


def test_get_order_status_case_insensitive():
    result = get_order_status("ord-001", _ctx())
    assert result["found"] is True


# cancel_order

def test_cancel_order_delivered_cannot_cancel():
    # ORD-003 is Delivered
    result = cancel_order("ORD-003", _ctx())
    assert result["cancelled"] is False


def test_cancel_order_already_cancelled():
    # ORD-004 is Cancelled
    result = cancel_order("ORD-004", _ctx())
    assert result["cancelled"] is False


def test_cancel_order_not_found():
    result = cancel_order("ORD-999", _ctx())
    assert result["cancelled"] is False


def test_cancel_order_invalid_format():
    result = cancel_order("NOTANORDER", _ctx())
    assert result.get("cancelled") is False or "error" in result


# save_customer_name

def test_save_customer_name_success():
    ctx = _ctx()
    result = save_customer_name("Priya", ctx)
    assert result["saved"] is True
    assert ctx.state.get("current_customer_name") == "Priya"


def test_save_customer_name_empty():
    ctx = _ctx()
    result = save_customer_name("", ctx)
    # Should either refuse or save empty; must not raise
    assert isinstance(result, dict)


# Mock data sanity

def test_mock_orders_contains_expected_ids():
    for oid in ("ORD-001", "ORD-002", "ORD-003", "ORD-004", "ORD-005"):
        assert oid in MOCK_ORDERS
