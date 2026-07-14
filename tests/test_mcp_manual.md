# Day 08 — FastMCP Integration Manual Tests

## Starting MCP servers

```bash
# Orders server (HTTP) — started automatically by support_agent.py import
# Inventory server (stdio) — spawned per McpToolset connection

# Manual test (start servers separately):
python src/services/mcp_servers/orders_server.py &  # port 8766

# List tools (requires mcp CLI or httpx):
python -c "
import httpx, json
r = httpx.post('http://127.0.0.1:8766/mcp', json={'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}})
print(json.dumps(r.json(), indent=2))
"
```

## Test scenarios

| # | Query | Expected MCP call | Expected result |
|---|-------|-------------------|-----------------|
| 1 | "Where is ORD-001?" | `get_order_status("ORD-001")` | Shipped, BlueDart, 2 Jul 2026 |
| 2 | "Give me full details for ORD-003" | `get_order_details("ORD-003")` | Delivered, items list |
| 3 | "List all orders for Priya Sharma" | `list_orders("Priya Sharma")` | ORD-001 + ORD-005 |
| 4 | "Cancel ORD-002" | `cancel_order_mcp("ORD-002")` | Preview → confirm → cancelled |
| 5 | "Is the 4K TV in stock? (PRD-102)" | `check_stock("PRD-102")` | Out of stock |
| 6 | "What TV models do you have?" | `list_variants("television")` | PRD-102 + PRD-106 |
| 7 | Cancel already-cancelled order | `cancel_order_mcp("ORD-004")` | "already cancelled" error |

## Timeout scenario

Set `INVENTORY_SEARCH_DELAY_SECONDS=8` and `INVENTORY_TOOL_TIMEOUT_SECONDS=3` in .env.
Ask "Is the keyboard in stock?" — expected: graceful `{"error": ...}` from MCP toolset,
agent reports "inventory service temporarily unavailable" (no crash).

## Run with MCP agent

```bash
SESSION_BACKEND=memory DEMO_AGENT=mcp python demo.py
```
