"""
product_tools.py — eComBot product lookup tool
------------------------------------------------
PostgreSQL-backed product catalog queries. Falls back to mock data when
SESSION_BACKEND=memory.

Tool context writes (working memory):
  lookup_product → current_product_id, last_product_name, last_intent, last_lookup_key
"""

import logging
import os
from typing import Any

from google.adk.tools import ToolContext

log = logging.getLogger(__name__)

# Mock product catalog
MOCK_PRODUCTS: list[dict[str, Any]] = [
    {
        "product_id": "PRD-101",
        "name": "Noise-Cancelling Headphones XB500",
        "category": "Audio",
        "price": 149.99,
        "stock_qty": 42,
        "description": "Over-ear wireless headphones with 30h battery and active noise cancellation.",
        "active": True,
    },
    {
        "product_id": "PRD-102",
        "name": "4K Smart TV 55-inch",
        "category": "Television",
        "price": 699.00,
        "stock_qty": 0,
        "description": "55-inch 4K UHD Smart TV with built-in streaming apps and HDR10 support.",
        "active": True,
    },
    {
        "product_id": "PRD-103",
        "name": "Mechanical Keyboard Pro",
        "category": "Peripherals",
        "price": 89.99,
        "stock_qty": 120,
        "description": "Tenkeyless mechanical keyboard with Cherry MX Red switches and RGB backlight.",
        "active": True,
    },
    {
        "product_id": "PRD-104",
        "name": "Wireless Earbuds Ultra",
        "category": "Audio",
        "price": 79.99,
        "stock_qty": 65,
        "description": "True wireless earbuds with ANC, 24h total battery, and IPX5 water resistance.",
        "active": True,
    },
    {
        "product_id": "PRD-105",
        "name": "Gaming Mouse RGB",
        "category": "Peripherals",
        "price": 49.99,
        "stock_qty": 0,
        "description": "High-precision gaming mouse with 16000 DPI sensor and customizable RGB zones.",
        "active": False,
    },
]

def _use_mock() -> bool:
    return os.getenv("SESSION_BACKEND", "memory").lower() == "memory"

# Tool: lookup_product
def lookup_product(
    product_name: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """
    Search the product catalog by name and return matching product details.
    Stores the looked-up product in session state for follow-up questions.

    Args:
        product_name: Full or partial product name to search for, e.g. "headphones".

    Returns:
        A dict with matched product details, or an error dict if nothing found.
    """
    if not product_name or not product_name.strip():
        return {"found": False, "error": "Product name cannot be empty. Please provide a product name to search."}

    search = product_name.strip()

    if _use_mock():
        # Memory mode: simple substring search on mock data
        matches = [
            p for p in MOCK_PRODUCTS
            if search.lower() in p["name"].lower() and p["active"]
        ]
    else:
        # PostgreSQL full-text / ILIKE search
        try:
            from services.db import query_all
            matches = query_all(
                """
                SELECT product_id, name, category, price, stock_qty, description, active
                FROM products
                WHERE active = true
                  AND (LOWER(name) LIKE LOWER(%s) OR LOWER(category) LIKE LOWER(%s))
                ORDER BY name ASC
                LIMIT 5
                """,
                (f"%{search}%", f"%{search}%"),
            )
        except Exception as exc:
            log.error("DB error in lookup_product: %s", exc)
            return {"found": False, "error": "Product search is temporarily unavailable. Please try again shortly."}

    if not matches:
        return {
            "found": False,
            "query": search,
            "error": f"No products found matching '{search}'. Try a shorter or different keyword.",
        }

    # Use first match for session state
    first = matches[0]
    tool_context.state["current_product_id"] = first["product_id"]
    tool_context.state["last_product_name"] = first["name"]
    tool_context.state["last_intent"] = "product_lookup"
    tool_context.state["last_lookup_key"] = first["product_id"]

    results = []
    for p in matches:
        availability = "In Stock" if p["stock_qty"] > 0 else "Out of Stock"
        results.append({
            "product_id": p["product_id"],
            "name": p["name"],
            "category": p["category"],
            "price_usd": float(p["price"]),
            "availability": availability,
            "stock_qty": p["stock_qty"],
            "description": p["description"],
        })

    return {
        "found": True,
        "query": search,
        "count": len(results),
        "products": results,
    }
