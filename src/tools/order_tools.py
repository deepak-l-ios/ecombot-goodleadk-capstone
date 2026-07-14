"""
order_tools.py — eComBot order tools
======================================
PostgreSQL-backed order queries. Falls back to mock data when
SESSION_BACKEND=memory.

Tool context writes (working memory):
  save_customer_name → current_customer_name
  get_order_status   → current_order_id, current_customer_name, last_intent, last_lookup_key
  cancel_order       → current_order_id, last_intent, last_lookup_key
"""

import logging
import re
from typing import Any

from google.adk.tools import ToolContext

log = logging.getLogger(__name__)

# ORDER_ID validation
_ORDER_ID_RE = re.compile(r"^ORD-\d+$", re.IGNORECASE)

# Mock data for offline / unit-test use
MOCK_ORDERS: dict[str, dict[str, Any]] = {
    "ORD-001": {
        "order_id": "ORD-001",
        "customer_name": "Priya Sharma",
        "product_name": "Noise-Cancelling Headphones XB500",
        "status": "Shipped",
        "eta": "2 Jul 2026",
        "carrier": "BlueDart",
    },
    "ORD-002": {
        "order_id": "ORD-002",
        "customer_name": "Ravi Patel",
        "product_name": "4K Smart TV 55-inch",
        "status": "Processing",
        "eta": "5 Jul 2026",
        "carrier": "DTDC",
    },
    "ORD-003": {
        "order_id": "ORD-003",
        "customer_name": "Aisha Mehta",
        "product_name": "Mechanical Keyboard Pro",
        "status": "Delivered",
        "eta": "Already delivered",
        "carrier": "FedEx",
    },
    "ORD-004": {
        "order_id": "ORD-004",
        "customer_name": "James Liu",
        "product_name": "Wireless Earbuds Ultra",
        "status": "Cancelled",
        "eta": "N/A",
        "carrier": "N/A",
    },
    "ORD-005": {
        "order_id": "ORD-005",
        "customer_name": "Maria Santos",
        "product_name": "Gaming Mouse RGB",
        "status": "Out for Delivery",
        "eta": "Today",
        "carrier": "Delhivery",
    },
}

def _use_mock() -> bool:
    """Return True when PostgreSQL is not configured (SESSION_BACKEND=memory)."""
    import os
    return os.getenv("SESSION_BACKEND", "memory").lower() == "memory"

# Tool: get_order_status
def get_order_status(
    order_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """
    Return the current status of a customer's order.
    Stores the customer name and order ID in session state for follow-ups.

    Args:
        order_id: The order reference in format ORD-XXX, e.g. "ORD-001".

    Returns:
        A dict with order details, or an error dict if not found or invalid.
    """
    if not order_id or not order_id.strip():
        return {"found": False, "error": "Order ID cannot be empty. Please provide your order reference (e.g. ORD-001)."}

    oid = order_id.strip().upper()

    if not _ORDER_ID_RE.match(oid):
        return {
            "found": False,
            "order_id": oid,
            "error": f"'{oid}' is not a valid order ID format. Order IDs look like ORD-001. Please check and try again.",
        }

    if _use_mock():
        # In-memory mock data
        row = MOCK_ORDERS.get(oid)
    else:
        # PostgreSQL
        try:
            from services.db import query_one
            row = query_one("SELECT * FROM orders WHERE order_id = %s", (oid,))
        except Exception as exc:
            log.error("DB error in get_order_status: %s", exc)
            return {"found": False, "error": "Order lookup is temporarily unavailable. Please try again shortly."}

    if row is None:
        return {
            "found": False,
            "order_id": oid,
            "error": f"No order found for '{oid}'. Please check your order reference and try again.",
        }

    # Write to session state for follow-up turns
    tool_context.state["current_order_id"] = oid
    tool_context.state["current_customer_name"] = row.get("customer_name", "")
    tool_context.state["last_intent"] = "order_status"
    tool_context.state["last_lookup_key"] = oid

    return {
        "found": True,
        "order_id": row["order_id"],
        "customer_name": row["customer_name"],
        "product_name": row["product_name"],
        "status": row["status"],
        "eta": row["eta"],
        "carrier": row["carrier"],
    }

# Tool: cancel_order
def cancel_order(
    order_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """
    Cancel an order by order ID.
    If order_id is "current" or empty, uses the last looked-up order from session state.
    Rejects already-cancelled orders with a clear message.

    Args:
        order_id: The order reference (e.g. "ORD-001"), or "current" to use session context.

    Returns:
        A dict indicating success or the reason cancellation failed.
    """
    # Resolve "current" shorthand from session state
    if not order_id or order_id.strip().lower() in ("", "current"):
        order_id = tool_context.state.get("current_order_id", "")

    if not order_id:
        return {
            "cancelled": False,
            "error": "No order ID provided or found in this session. Please provide your order reference (e.g. ORD-001).",
        }

    oid = order_id.strip().upper()

    if not _ORDER_ID_RE.match(oid):
        return {
            "cancelled": False,
            "order_id": oid,
            "error": f"'{oid}' is not a valid order ID format. Order IDs look like ORD-001.",
        }

    if _use_mock():
        # In-memory mock — mutate the dict
        row = MOCK_ORDERS.get(oid)
        if row is None:
            return {"cancelled": False, "order_id": oid, "error": f"Order '{oid}' not found."}
        if row["status"].lower() == "cancelled":
            return {
                "cancelled": False,
                "order_id": oid,
                "error": f"Order '{oid}' is already cancelled. No changes were made.",
            }
        MOCK_ORDERS[oid]["status"] = "Cancelled"
        customer_name = row["customer_name"]
    else:
        # PostgreSQL
        try:
            from services.db import execute, query_one
            row = query_one(
                "SELECT status, customer_name FROM orders WHERE order_id = %s", (oid,)
            )
        except Exception as exc:
            log.error("DB error in cancel_order lookup: %s", exc)
            return {"cancelled": False, "error": "Cancellation service is temporarily unavailable. Please try again shortly."}

        if row is None:
            return {"cancelled": False, "order_id": oid, "error": f"Order '{oid}' not found."}

        if row["status"].lower() == "cancelled":
            return {
                "cancelled": False,
                "order_id": oid,
                "error": f"Order '{oid}' is already cancelled. No changes were made.",
            }

        try:
            execute("UPDATE orders SET status = 'Cancelled' WHERE order_id = %s", (oid,))
        except Exception as exc:
            log.error("DB error updating order: %s", exc)
            return {"cancelled": False, "error": "Cancellation could not be saved. Please try again."}

        customer_name = row["customer_name"]

    tool_context.state["current_order_id"] = oid
    tool_context.state["last_intent"] = "cancel_order"
    tool_context.state["last_lookup_key"] = oid

    return {
        "cancelled": True,
        "order_id": oid,
        "customer_name": customer_name,
        "message": f"Order {oid} for {customer_name} has been successfully cancelled.",
    }

# Tool: save_customer_name
def save_customer_name(
    name: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """
    Save the customer's name to session state.
    Call this as soon as the customer introduces themselves so follow-up
    replies can use their name without asking again.

    Args:
        name: The customer's name as provided by them.

    Returns:
        A dict confirming the name was saved.
    """
    if not name or not name.strip():
        return {"saved": False, "error": "Name cannot be empty."}

    clean = name.strip()
    tool_context.state["current_customer_name"] = clean
    tool_context.state["last_intent"] = "greeting"

    return {"saved": True, "customer_name": clean}
