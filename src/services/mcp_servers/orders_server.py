"""
orders_server.py — eComBot Order Management MCP tool server
============================================================
A FastMCP server exposing order-management tools over Streamable HTTP.
support_agent.py starts this as a background subprocess and connects to
it with McpToolset/StreamableHTTPConnectionParams.

Tools:
  get_order_status(order_id)         → quick status lookup
  get_order_details(order_id)        → full order record
  list_orders(customer_name)         → all orders for a customer
  cancel_order_mcp(order_id, confirm=False)
                                      → cancel ONE order; requires confirm=True

Run directly for local testing:
    python src/services/mcp_servers/orders_server.py
    # serves on http://127.0.0.1:8766/mcp by default
"""

import os

from mcp.server.fastmcp import FastMCP

# WARNING level — keep the demo's console output free of per-request noise.
mcp = FastMCP(
    "ecombot-orders",
    log_level="WARNING",
    host=os.getenv("ORDERS_SERVER_HOST", "127.0.0.1"),
    port=int(os.getenv("ORDERS_SERVER_PORT", "8766")),
)

# Mock order data — mirrors order_tools.py MOCK_ORDERS
_ORDERS: dict[str, dict] = {
    "ORD-001": {
        "order_id": "ORD-001",
        "customer_name": "Priya Sharma",
        "product_name": "Noise-Cancelling Headphones XB500",
        "status": "Shipped",
        "eta": "2 Jul 2026",
        "carrier": "BlueDart",
        "items": [{"product_id": "PRD-101", "qty": 1, "price": 149.99}],
    },
    "ORD-002": {
        "order_id": "ORD-002",
        "customer_name": "Ravi Patel",
        "product_name": "4K Smart TV 55-inch",
        "status": "Processing",
        "eta": "5 Jul 2026",
        "carrier": "DTDC",
        "items": [{"product_id": "PRD-102", "qty": 1, "price": 699.00}],
    },
    "ORD-003": {
        "order_id": "ORD-003",
        "customer_name": "Aisha Mehta",
        "product_name": "Mechanical Keyboard Pro",
        "status": "Delivered",
        "eta": "Already delivered",
        "carrier": "FedEx",
        "items": [{"product_id": "PRD-103", "qty": 2, "price": 89.99}],
    },
    "ORD-004": {
        "order_id": "ORD-004",
        "customer_name": "James Liu",
        "product_name": "Wireless Earbuds Ultra",
        "status": "Cancelled",
        "eta": "N/A",
        "carrier": "N/A",
        "items": [{"product_id": "PRD-104", "qty": 1, "price": 79.99}],
    },
    "ORD-005": {
        "order_id": "ORD-005",
        "customer_name": "Priya Sharma",
        "product_name": "Gaming Mouse RGB",
        "status": "Processing",
        "eta": "7 Jul 2026",
        "carrier": "BlueDart",
        "items": [{"product_id": "PRD-105", "qty": 1, "price": 59.99}],
    },
}

def _not_found(order_id: str) -> dict:
    return {
        "found": False,
        "order_id": order_id,
        "message": (
            f"No order found with ID '{order_id}'. Double-check the "
            "reference (format: ORD-XXX) or check your email for confirmation."
        ),
    }

@mcp.tool()
def get_order_status(order_id: str) -> dict:
    """Look up the current status of a single order by its reference.

    Args:
        order_id: Order reference, e.g. "ORD-001".

    Returns:
        A dict with order_id, product_name, status, eta and carrier if found,
        or {"found": False, ...} with a guidance message if not.
    """
    order = _ORDERS.get(order_id.strip().upper())
    if order is None:
        return _not_found(order_id)

    return {
        "found": True,
        "order_id": order["order_id"],
        "product_name": order["product_name"],
        "status": order["status"],
        "eta": order["eta"],
        "carrier": order["carrier"],
    }

@mcp.tool()
def get_order_details(order_id: str) -> dict:
    """Fetch the full record for a single order including all line items.

    Args:
        order_id: Order reference, e.g. "ORD-002".

    Returns:
        The full order record (customer, product, status, items) if found,
        or {"found": False, ...} if not.
    """
    order = _ORDERS.get(order_id.strip().upper())
    if order is None:
        return _not_found(order_id)

    return {"found": True, **order}

@mcp.tool()
def list_orders(customer_name: str) -> dict:
    """List all orders for a customer by name.

    Use this when the user does not know their order reference, or when a
    request could affect more than one order.

    Args:
        customer_name: Customer's full name, e.g. "Priya Sharma".

    Returns:
        A dict with customer_name and a list of orders (order_id,
        product_name, status, eta). The list is empty if no orders match.
    """
    name_norm = customer_name.strip().lower()
    matches = [
        {
            "order_id": o["order_id"],
            "product_name": o["product_name"],
            "status": o["status"],
            "eta": o["eta"],
        }
        for o in _ORDERS.values()
        if o["customer_name"].lower() == name_norm
    ]

    result: dict = {"customer_name": customer_name, "orders": matches}
    if not matches:
        result["message"] = f"No orders found for '{customer_name}'."
    return result

@mcp.tool()
def cancel_order_mcp(order_id: str, confirm: bool = False) -> dict:
    """Cancel a single order. Requires explicit confirmation.

    This tool only ever cancels ONE order_id — there is intentionally no
    way to cancel multiple orders in one call. If the user asks to cancel
    "all" orders, use list_orders to show candidates and ask which one.

    Args:
        order_id: Order reference to cancel, e.g. "ORD-002".
        confirm: Must be True to actually cancel. Call first with
            confirm=False (or omitted) to preview, then call again with
            confirm=True only after the user explicitly agrees.

    Returns:
        Preview dict if confirm=False; cancellation result if confirm=True.
        Returns {"found": False, ...} if the order does not exist.
    """
    order = _ORDERS.get(order_id.strip().upper())
    if order is None:
        return _not_found(order_id)

    if order["status"] == "Cancelled":
        return {
            "cancelled": False,
            "order_id": order_id,
            "message": f"Order {order_id} is already cancelled.",
        }

    if order["status"] == "Delivered":
        return {
            "cancelled": False,
            "order_id": order_id,
            "message": (
                f"Order {order_id} has already been delivered and cannot be cancelled. "
                "Please contact support to request a return."
            ),
        }

    if not confirm:
        return {
            "cancelled": False,
            "order_id": order_id,
            "product_name": order["product_name"],
            "status": order["status"],
            "preview": True,
            "message": (
                f"Order {order_id} ({order['product_name']}) is currently '{order['status']}'. "
                "Call cancel_order_mcp again with confirm=True to proceed with cancellation."
            ),
        }

    # Mutate mock state and cancel
    _ORDERS[order_id.strip().upper()]["status"] = "Cancelled"
    _ORDERS[order_id.strip().upper()]["eta"] = "N/A"
    return {
        "cancelled": True,
        "order_id": order_id,
        "product_name": order["product_name"],
        "message": f"Order {order_id} ({order['product_name']}) has been successfully cancelled.",
    }


@mcp.tool()
def get_invoice(order_id: str) -> dict:
    """Generate an invoice for a shipped, delivered, or cancelled order.

    Args:
        order_id: Order reference, e.g. "ORD-001".

    Returns:
        Invoice dict with line items, subtotal, 18% GST, and total.
        Returns invoice_available=False for orders still in Processing.
    """
    order = _ORDERS.get(order_id.strip().upper())
    if order is None:
        return _not_found(order_id)

    eligible = {"Shipped", "Delivered", "Cancelled", "Out for Delivery"}
    if order["status"] not in eligible:
        return {
            "found": True,
            "invoice_available": False,
            "order_id": order_id,
            "message": (
                f"Invoice not yet available — order {order_id} is still "
                f"'{order['status']}'. An invoice will be generated once "
                "the order has shipped."
            ),
        }

    items = order.get("items", [{"product_id": "unknown", "qty": 1, "price": 0.0}])
    subtotal = round(sum(item["qty"] * item["price"] for item in items), 2)
    tax = round(subtotal * 0.18, 2)  # 18% GST
    total = round(subtotal + tax, 2)

    return {
        "found": True,
        "invoice_available": True,
        "order_id": order_id,
        "customer_name": order["customer_name"],
        "product_name": order["product_name"],
        "status": order["status"],
        "items": items,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "currency": "USD",
        "message": f"Invoice for order {order_id} — total: ${total} (incl. GST)",
    }


if __name__ == "__main__":
    mcp.run()
