"""
agents/sub_agent_patterns.py — Native ADK multi-agent patterns
================================================================
Three independent demo patterns using ADK's built-in multi-agent building
blocks:

  A. Agent routing (sub_agents + transfer_to_agent)
       concierge_agent
         +- product_discovery_agent   (lookup_product)
         +- order_support_agent       (get_order_status, cancel_order)

     concierge_agent has no tools itself. ADK gives every agent in this tree
     a transfer_to_agent tool. A transfer hands the whole turn (and, for the
     rest of the session, the conversation) to the target agent, including
     peer-to-peer handoffs between specialists.

  B. Sequential workflow graph (Workflow + edges)
       order_assist_pipeline = Workflow(edges=[
           (START, order_lookup_step, recommendation_step, summary_step),
       ])

     Each step writes its result to session state via output_key, and the
     next step's instruction pulls it back in with {state_key} templating.

  C. Parallel + sequential workflow graph (fan-out, then fan-in)
       product_join = JoinNode(name="product_join")
       product_research_pipeline = Workflow(edges=[
           (START, specs_researcher, product_join),
           (START, alternatives_researcher, product_join),
           (product_join, comparison_synthesizer),
       ])

     Two independent specialists run concurrently from START (fan-out),
     then comparison_synthesizer reads both and produces one recommendation
     (fan-in).
"""

import logging
import os

import litellm
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.workflow import JoinNode, START, Workflow

from tools.order_tools import get_order_status, cancel_order
from tools.product_tools import lookup_product

# Silence noisy loggers
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
os.environ.setdefault("LITELLM_LOG", "ERROR")
for _name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.CRITICAL)
    _log.propagate = False

litellm.suppress_debug_info = True
load_dotenv()

_MODEL = os.getenv("FAST_MODEL", "openrouter/google/gemini-2.5-flash")

# ═══════════════════════════════════════════════════════════════════════════
# Pattern A — Agent routing via sub_agents + transfer_to_agent
# ═══════════════════════════════════════════════════════════════════════════

_PRODUCT_PERSONA = """
You are eComBot's Product Discovery specialist, speaking directly with the customer.
Help them find the right electronics product using lookup_product(query).

Rules:
  - Call lookup_product before recommending anything — don't invent specs.
  - Group results by category when multiple products are returned.
  - If lookup_product finds nothing for the query, say so plainly.
  - If the customer then asks about an order or shipping, that's outside
    your area — hand the conversation off to the order support specialist.
""".strip()

product_discovery_agent = LlmAgent(
    name="product_discovery_agent",
    model=LiteLlm(model=_MODEL),
    instruction=_PRODUCT_PERSONA,
    description="Product Discovery specialist - product search, specs, comparisons, and recommendations.",
    tools=[lookup_product],
)

_ORDER_SUPPORT_PERSONA = """
You are eComBot's Order Support specialist, speaking directly with the customer.
Help them check order status or cancel an order using get_order_status and cancel_order.

Rules:
  - Look up by order_id if the customer gave one (format: ORD-XXX).
  - Tool results are structured data. Summarise in plain language — don't dump raw JSON.
  - For cancellations, confirm the order_id before calling cancel_order.
  - If the result has "found": false or an "error" field, explain plainly
    what happened and suggest a next step.
  - If the customer then asks about products or comparisons, that's outside
    your area — hand the conversation off to the product discovery specialist.
""".strip()

order_support_agent = LlmAgent(
    name="order_support_agent",
    model=LiteLlm(model=_MODEL),
    instruction=_ORDER_SUPPORT_PERSONA,
    description="Order Support specialist - order status lookups and order cancellations.",
    tools=[get_order_status, cancel_order],
)

_CONCIERGE_PERSONA = """
You are eComBot's front-desk Concierge. Greet customers and answer
general questions about what eComBot can do.

You have no order or product tools yourself — if a request needs
one, hand it off to the specialist who covers it rather than guessing.
""".strip()

# Pattern A: concierge with sub_agents — no tools, relies on transfer_to_agent
concierge_agent = LlmAgent(
    name="concierge_agent",
    model=LiteLlm(model=_MODEL),
    instruction=_CONCIERGE_PERSONA,
    description=(
        "eComBot front desk - greets customers and routes product questions "
        "to the Product Discovery specialist and order questions to the "
        "Order Support specialist."
    ),
    sub_agents=[product_discovery_agent, order_support_agent],
)

# ═══════════════════════════════════════════════════════════════════════════
# Pattern B — Workflow: a fixed pipeline graph (one path from START)
# ═══════════════════════════════════════════════════════════════════════════

_ORDER_LOOKUP_STEP_PERSONA = """
Step 1 of the order-assist pipeline. Look up the customer's order with
get_order_status(order_id), using the order ID in the request (format: ORD-XXX).

Write a short (1-2 sentence) summary of the order status — if it's
delayed or out for delivery, include the ETA and carrier. If nothing matches,
say so plainly. This summary is read by the next step, not shown to the
customer directly.
""".strip()

order_lookup_step = LlmAgent(
    name="order_lookup_step",
    model=LiteLlm(model=_MODEL),
    instruction=_ORDER_LOOKUP_STEP_PERSONA,
    description="Pipeline step 1 - looks up the customer's order status.",
    tools=[get_order_status],
    output_key="order_summary",
)

_RECOMMENDATION_STEP_PERSONA = """
Step 2 of the order-assist pipeline. Based on the order status from step 1,
use lookup_product to find products relevant to the customer's original request.

Order status from step 1:
{order_summary}

If the order is already delivered, suggest accessories or complementary products.
If the order is processing or shipped, reassure the customer and suggest related items.
If cancelled, suggest the same or equivalent products they can reorder.
Keep it brief (2-3 product mentions). This is read by the next step, not shown directly.
""".strip()

recommendation_step = LlmAgent(
    name="recommendation_step",
    model=LiteLlm(model=_MODEL),
    instruction=_RECOMMENDATION_STEP_PERSONA,
    description="Pipeline step 2 - suggests complementary products based on order context.",
    tools=[lookup_product],
    output_key="product_suggestions",
)

_SUMMARY_STEP_PERSONA = """
Step 3 of the order-assist pipeline — the only step the customer sees.
Combine the results below into one friendly summary: order status first,
then the product suggestions. Don't repeat yourself or add new information
— just combine what's given here in a warm, helpful tone.

Order status:
{order_summary}

Product suggestions:
{product_suggestions}
""".strip()

summary_step = LlmAgent(
    name="summary_step",
    model=LiteLlm(model=_MODEL),
    instruction=_SUMMARY_STEP_PERSONA,
    description="Pipeline step 3 - combines order status and product suggestions into one customer-facing reply.",
    output_key="order_assist_recap",
)

order_assist_pipeline = Workflow(
    name="order_assist_pipeline",
    description=(
        "Order-assist pipeline - checks an order, suggests complementary products, "
        "then recaps both in one reply. Always runs in this fixed order."
    ),
    edges=[
        (START, order_lookup_step, recommendation_step, summary_step),
    ],
)

# ═══════════════════════════════════════════════════════════════════════════
# Pattern C — Workflow: fan-out from START, JoinNode fan-in
# ═══════════════════════════════════════════════════════════════════════════

_SPECS_RESEARCH_PERSONA = """
Research step (runs concurrently with alternatives research). Use
lookup_product(query) for the product in the request and list the specs
it returns — name, price, category, stock, and key description points.
This is raw research for a later step, not shown to the customer directly.
""".strip()

specs_researcher = LlmAgent(
    name="specs_researcher",
    model=LiteLlm(model=_MODEL),
    instruction=_SPECS_RESEARCH_PERSONA,
    description="Research step - looks up detailed specs for the requested product.",
    tools=[lookup_product],
    output_key="specs_findings",
)

_ALTERNATIVES_RESEARCH_PERSONA = """
Research step (runs concurrently with specs research). Use
lookup_product(query) with a broader query (e.g. the product category)
to find 2-3 alternative or comparable products to the one in the request.
List their names, prices, and key differentiators.
This is raw research for a later step, not shown to the customer directly.
""".strip()

alternatives_researcher = LlmAgent(
    name="alternatives_researcher",
    model=LiteLlm(model=_MODEL),
    instruction=_ALTERNATIVES_RESEARCH_PERSONA,
    description="Research step - finds alternative or comparable products.",
    tools=[lookup_product],
    output_key="alternatives_findings",
)

_COMPARISON_SYNTHESIS_PERSONA = """
Final step — the only one the customer sees. Combine the research below
into a clear product comparison and recommendation.

Product specs:
{specs_findings}

Alternatives found:
{alternatives_findings}

Give the customer a side-by-side comparison (name, price, key pros/cons)
and a clear recommendation based on value for money and features.
Briefly mention *why* you recommended the one you did.
""".strip()

comparison_synthesizer = LlmAgent(
    name="comparison_synthesizer",
    model=LiteLlm(model=_MODEL),
    instruction=_COMPARISON_SYNTHESIS_PERSONA,
    description="Final step - combines product specs and alternatives into one comparison and recommendation.",
    output_key="product_comparison",
)

product_join = JoinNode(name="product_join")

product_research_pipeline = Workflow(
    name="product_research_pipeline",
    description=(
        "Researches a product's specs and alternatives in parallel, "
        "then synthesizes both into one comparison and recommendation."
    ),
    edges=[
        (START, specs_researcher, product_join),
        (START, alternatives_researcher, product_join),
        (product_join, comparison_synthesizer),
    ],
)
