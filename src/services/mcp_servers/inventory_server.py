"""
inventory_server.py — eComBot Inventory MCP tool server
=========================================================
A FastMCP server exposing inventory tools over stdio.
support_agent.py spawns this as a subprocess via StdioConnectionParams.

Tools:
  check_stock(product_id)               → current stock level
  list_variants(product_family)         → available variants/models

Set INVENTORY_SEARCH_DELAY_SECONDS to simulate a slow upstream API
and demonstrate MCP timeout handling.

Run directly for local testing:
    python src/services/mcp_servers/inventory_server.py
"""

import asyncio
import os

from mcp.server.fastmcp import FastMCP

# WARNING level — keep demo console output free of per-request noise.
mcp = FastMCP("ecombot-inventory", log_level="WARNING")

# Mock inventory data — mirrors product_tools.py MOCK_PRODUCTS
_PRODUCTS: dict[str, dict] = {
    "PRD-101": {
        "product_id": "PRD-101",
        "name": "Noise-Cancelling Headphones XB500",
        "category": "Audio",
        "price": 149.99,
        "stock_qty": 42,
        "active": True,
    },
    "PRD-102": {
        "product_id": "PRD-102",
        "name": "4K Smart TV 55-inch",
        "category": "Television",
        "price": 699.00,
        "stock_qty": 0,
        "active": True,
    },
    "PRD-103": {
        "product_id": "PRD-103",
        "name": "Mechanical Keyboard Pro",
        "category": "Peripherals",
        "price": 89.99,
        "stock_qty": 120,
        "active": True,
    },
    "PRD-104": {
        "product_id": "PRD-104",
        "name": "Wireless Earbuds Ultra",
        "category": "Audio",
        "price": 79.99,
        "stock_qty": 65,
        "active": True,
    },
    "PRD-105": {
        "product_id": "PRD-105",
        "name": "Gaming Mouse RGB",
        "category": "Peripherals",
        "price": 59.99,
        "stock_qty": 18,
        "active": True,
    },
    "PRD-106": {
        "product_id": "PRD-106",
        "name": "8K OLED TV 65-inch",
        "category": "Television",
        "price": 1999.00,
        "stock_qty": 5,
        "active": True,
    },
    "PRD-107": {
        "product_id": "PRD-107",
        "name": "True Wireless Earbuds Pro",
        "category": "Audio",
        "price": 129.99,
        "stock_qty": 0,
        "active": False,
    },
}

# Product family → variant list
_VARIANTS: dict[str, list[dict]] = {
    "television": [
        {"product_id": "PRD-102", "name": "4K Smart TV 55-inch", "price": 699.00, "in_stock": False},
        {"product_id": "PRD-106", "name": "8K OLED TV 65-inch",  "price": 1999.00, "in_stock": True},
    ],
    "audio": [
        {"product_id": "PRD-101", "name": "Noise-Cancelling Headphones XB500", "price": 149.99, "in_stock": True},
        {"product_id": "PRD-104", "name": "Wireless Earbuds Ultra",             "price": 79.99,  "in_stock": True},
        {"product_id": "PRD-107", "name": "True Wireless Earbuds Pro",          "price": 129.99, "in_stock": False},
    ],
    "peripherals": [
        {"product_id": "PRD-103", "name": "Mechanical Keyboard Pro", "price": 89.99, "in_stock": True},
        {"product_id": "PRD-105", "name": "Gaming Mouse RGB",         "price": 59.99, "in_stock": True},
    ],
}

@mcp.tool()
async def check_stock(product_id: str) -> dict:
    """Check the current stock level for a single product.

    Args:
        product_id: Product reference, e.g. "PRD-102".

    Returns:
        A dict with product_id, name, stock_qty and in_stock flag, or
        {"found": False, ...} if the product ID is not recognised.
    """
    delay = float(os.getenv("INVENTORY_SEARCH_DELAY_SECONDS", "0"))
    if delay > 0:
        await asyncio.sleep(delay)

    product = _PRODUCTS.get(product_id.strip().upper())
    if product is None:
        return {
            "found": False,
            "product_id": product_id,
            "message": (
                f"No product found with ID '{product_id}'. "
                "Valid IDs look like PRD-XXX."
            ),
        }

    return {
        "found": True,
        "product_id": product["product_id"],
        "name": product["name"],
        "stock_qty": product["stock_qty"],
        "in_stock": product["stock_qty"] > 0,
        "active": product["active"],
    }

@mcp.tool()
async def list_variants(product_family: str) -> dict:
    """List all available models/variants in a product family.

    Args:
        product_family: Category name, e.g. "television", "audio",
            "peripherals". Case-insensitive.

    Returns:
        A dict with product_family and a list of variant records
        (product_id, name, price, in_stock). Returns an empty list
        if the family is not recognised.
    """
    delay = float(os.getenv("INVENTORY_SEARCH_DELAY_SECONDS", "0"))
    if delay > 0:
        await asyncio.sleep(delay)

    family_lower = product_family.strip().lower()
    variants = _VARIANTS.get(family_lower)

    if variants is None:
        return {
            "product_family": product_family,
            "variants": [],
            "message": (
                f"No product family '{product_family}' found. "
                "Known families: television, audio, peripherals."
            ),
        }

    return {
        "product_family": product_family,
        "variants": variants,
    }

if __name__ == "__main__":
    mcp.run()
