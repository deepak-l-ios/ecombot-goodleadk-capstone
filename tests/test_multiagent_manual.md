# Day 09 — Multi-Agent Orchestration Manual Tests

Run: `SESSION_BACKEND=memory python demo.py`

## Routing verification

| # | Query | Expected route | Specialist called | Delegation trace |
|---|-------|----------------|-------------------|------------------|
| 1 | "Where is ORD-001?" | support | `delegate_to_support` | `get_order_status("ORD-001")` |
| 2 | "Cancel ORD-002" | support | `delegate_to_support` | `cancel_order(...)` |
| 3 | "Recommend headphones under $200" | sales | `delegate_to_sales` | `lookup_product("headphones")` |
| 4 | "Compare 4K TV vs 8K TV" | sales | `delegate_to_sales` | `lookup_product(...)` × 2 |
| 5 | "My ORD-002 arrived damaged. Suggest replacement TV" | both | support → then sales | both specialists |
| 6 | "Hi, what can you help me with?" | direct | (none) | (none) |
| 7 | "Who are you?" | direct | (none) | (none) |

## Expected delegation trace format (demo output)

```
[delegate→ecombot_support_deep] call  get_order_status({'order_id': 'ORD-001'})
[delegate→ecombot_support_deep] result get_order_status → {'found': True, 'order_id': 'ORD-001', ...}
```

## Negative cases

- **Specialist backend error**: Set `SESSION_BACKEND=bad` to force session error → orchestrator
  should report "temporarily unavailable" without crashing.
- **Unknown order**: Ask about ORD-999 → specialist returns `{"found": False}` → orchestrator
  relays gracefully.
