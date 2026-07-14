# Day 09a — Native ADK Multi-Agent Patterns Manual Tests

Run: `SESSION_BACKEND=memory python demo.py`  
The Day 09a section runs automatically after the Day 01-12 scenarios.

---

## Pattern A: sub_agents + transfer_to_agent (Agent routing)

| # | Agent | Input | Expected | Notes |
|---|-------|-------|----------|-------|
| A1 | concierge_agent | "Tell me about the Noise-Cancelling Headphones XB500." | Transferred to `product_discovery_agent`; lookups product specs via `lookup_product` | `transfer_to_agent` action visible in event stream |
| A2 | (same session, now in product_discovery_agent) | "What's the status of my order ORD-001?" | Peer-transferred to `order_support_agent` without going back to concierge | Peer-to-peer handoff |
| A3 | concierge_agent (new session) | "Hi! What can eComBot help me with?" | concierge_agent answers directly — no transfer | General greeting in concierge scope |

## Pattern B: Sequential Workflow (Workflow edges, START to end)

| # | Pipeline | Input | Expected | Notes |
|---|----------|-------|----------|-------|
| B1 | order_assist_pipeline | "Check ORD-001 and suggest something I might also like." | Step 1: order_lookup_step checks ORD-001 (status=Shipped); Step 2: recommendation_step suggests accessories; Step 3: summary_step combines into one reply | `output_key` chain: `order_summary` → `product_suggestions` → `order_assist_recap` |

## Pattern C: Parallel + fan-in Workflow (JoinNode)

| # | Pipeline | Input | Expected | Notes |
|---|----------|-------|----------|-------|
| C1 | product_research_pipeline | "Research the Noise-Cancelling Headphones XB500 and compare with alternatives." | `specs_researcher` and `alternatives_researcher` run concurrently; `product_join` merges; `comparison_synthesizer` produces final comparison + recommendation | Both branches complete before synthesis; may see both tool call traces |

---

## ADK Web exploration

To explore Pattern A interactively:

```bash
# In src/agents/sub_agent_patterns.py,
# the concierge_agent is the root-agent entry point
adk web src/agents/sub_agent_patterns.py
```
