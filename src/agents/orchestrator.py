"""
orchestrator.py — eComBot Multi-Agent Orchestrator
====================================================
Receives every user message, classifies intent, and delegates to the right
specialist via delegation tools. Does NOT call order or product tools itself.

Specialists:
  support_specialist — order status, cancellations, returns, support issues
  sales_specialist   — product discovery, comparisons, budget recommendations

For cross-domain queries it delegates to Support first, then Sales, passing
relevant context between them.
"""

import logging
import os

import litellm
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from session import make_runner

logging.getLogger("asyncio").setLevel(logging.CRITICAL)
os.environ.setdefault("LITELLM_LOG", "ERROR")
for _name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.CRITICAL)
    _log.propagate = False

litellm.suppress_debug_info = True
load_dotenv()

from agents.support_agent import deep_support_agent as _support_specialist
from agents.sales_agent import sales_agent as _sales_specialist
from routing import FAST_MODEL
from guardrails import injection_guardrail, output_pii_guardrail

# Delegation trace
# Populated by _run_specialist() while a delegation tool runs, and drained
# by demo.py / chainlit_app.py after each top-level turn.
delegation_trace: list[dict] = []

async def _run_specialist(agent: LlmAgent, request: str) -> str:
    """Run a specialist agent on `request` in its own runner/session.

    Records the specialist's tool calls/results into delegation_trace
    (tagged with the specialist's name), then returns its final reply text —
    this is what the Orchestrator's LLM sees as the tool result.
    """
    runner, user_id, session_id = await make_runner(agent)
    reply = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=request)]),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "function_call", None):
                    fc = part.function_call
                    delegation_trace.append(
                        {
                            "agent": agent.name,
                            "type": "call",
                            "tool": fc.name,
                            "args": dict(fc.args or {}),
                        }
                    )
                if getattr(part, "function_response", None):
                    fr = part.function_response
                    delegation_trace.append(
                        {
                            "agent": agent.name,
                            "type": "result",
                            "tool": fr.name,
                            "response": fr.response or {},
                        }
                    )
        if event.is_final_response():
            if event.content and event.content.parts:
                reply = event.content.parts[0].text or ""
    return reply.strip()

# Delegation tools
async def delegate_to_support(request: str) -> str:
    """Ask the Support specialist to handle an order or post-sales issue.

    Use this for:
    - Order status lookups (ORD-XXX references)
    - Order cancellations
    - Return and refund inquiries
    - Carrier or delivery questions
    - Post-purchase support issues

    Args:
        request: A self-contained description of the support request.
            Include the order ID (ORD-XXX) and customer name if known.
            Make the request fully self-contained so the specialist
            does not need the rest of the conversation to understand it.

    Returns:
        The Support specialist's reply, in plain language.
    """
    return await _run_specialist(_support_specialist, request)

async def delegate_to_sales(request: str) -> str:
    """Ask the Sales specialist to help with product discovery or recommendations.

    Use this for:
    - Product discovery queries ("phones under ₹20k", "4K TV options")
    - Product comparisons ("compare headphones A vs B")
    - Budget-constrained recommendations
    - Feature-based filtering ("laptop with 16GB RAM under $1000")
    - Product FAQ questions (warranty, specs, compatibility)

    Args:
        request: A self-contained description of the sales or product request.
            Include the budget, category, and any preference constraints
            the customer mentioned.

    Returns:
        The Sales specialist's reply, in plain language.
    """
    return await _run_specialist(_sales_specialist, request)

# Orchestrator persona
_ORCHESTRATOR_PERSONA = """
You are eComBot's Orchestrator. You coordinate two specialists:

  - A Support specialist, for order-related issues (status, cancellations,
    returns, delivery, and post-purchase problems).
  - A Sales specialist, for product discovery, comparisons, and
    budget-constrained recommendations.

Routing rules:
  - If the request is ONLY about an existing order (status, cancellation,
    return), delegate ONLY to the Support specialist.
  - If the request is ONLY about finding or comparing products (discovery,
    recommendations, specs, budget queries), delegate ONLY to the Sales
    specialist.
  - If the request involves BOTH (e.g. "my order was wrong, suggest a
    replacement"), delegate to Support first to understand the issue, then
    to Sales to recommend alternatives. Pass relevant context from Support
    to the Sales request so it is self-contained.
  - For general capability questions ("what can you help me with?") or
    simple greetings, answer directly yourself — do not delegate.
  - If the user gives their name, acknowledge it and remember it — you do
    not need to delegate this.

Delegation rules:
  - Each specialist only sees the request you send it, not the full
    conversation. Make every delegation request fully self-contained
    (include order IDs, budget constraints, product names, etc.).
  - If a specialist reports an error or unavailable tool, tell the user
    plainly and suggest a next step. Do not retry the same specialist.
  - Never invent order details or product data yourself — only relay what
    the specialists return.
  - Combine specialist results into a single, coherent reply to the user.
    Do not say "According to the Support agent…" — just report the result.
""".strip()

# Orchestrator agent
orchestrator = LlmAgent(
    name="ecombot_orchestrator",
    model=LiteLlm(model=FAST_MODEL),  # Orchestrator uses fast model; specialists handle reasoning
    instruction=_ORCHESTRATOR_PERSONA,
    description=(
        "eComBot Orchestrator: routes support queries to the Support specialist "
        "and sales queries to the Sales specialist. Handles greetings directly."
    ),
    tools=[delegate_to_support, delegate_to_sales],
    before_model_callback=injection_guardrail,
    after_model_callback=output_pii_guardrail,
)
