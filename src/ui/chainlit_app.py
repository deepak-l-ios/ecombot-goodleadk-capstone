"""
chainlit_app.py — eComBot Generative UI with Chainlit
=======================================================
Run:
    cp .env.example .env   # fill in OPENROUTER_API_KEY
    chainlit run src/ui/chainlit_app.py

Six UI pattern groups layered on top of the eComBot multi-agent backend
(Orchestrator → Support / Sales specialists):

  Group 1 — Messages + structured cards
  Group 2 — Steps for tool calls
  Group 3 — Action buttons (budget filter)
  Group 4 — Session state (customer_name, last_order_id, last_product_name)
  Group 5 — Progress + errors (guardrail block indicator)
  Group 6 — Explainability (type "show me how you made this")
"""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

import chainlit as cl
import litellm
from dotenv import load_dotenv
from google.genai import types

load_dotenv()

# Ensure src/ is importable
_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

logging.getLogger("asyncio").setLevel(logging.CRITICAL)
os.environ.setdefault("LITELLM_LOG", "ERROR")
for _name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.CRITICAL)
    _log.propagate = False
litellm.suppress_debug_info = True

from agents.orchestrator import orchestrator
from session import make_runner
from reasoning import run_turn as _reasoning_run_turn, TurnResult
from tracing import trace_turn
from routing import routing_log, enable_routing_callbacks, classify_query
from rag.retriever import retrieve

# Helpers
_TOOL_LABELS = {
    "get_order_status":   "Check order status",
    "cancel_order":       "Cancel order",
    "lookup_product":     "Search products",
    "save_customer_name": "Save customer name",
    "delegate_to_support": "Route to Support specialist",
    "delegate_to_sales":   "Route to Sales specialist",
    "get_order_status_mcp": "Check order (MCP)",
    "cancel_order_mcp":     "Cancel order (MCP)",
    "get_invoice":          "Get invoice",
    "check_stock":          "Check stock (MCP)",
    "list_variants":        "List variants (MCP)",
}

_EXPLAINABILITY_TRIGGERS = [
    "show me how", "how did you", "how was this", "how did this",
    "explain how", "walk me through",
]

_ORDER_RE = re.compile(r"\bORD-\d+\b", re.IGNORECASE)
_PRODUCT_RE = re.compile(
    r"\b(headphone|tv|television|keyboard|mouse|earbuds|laptop|phone)\b",
    re.IGNORECASE,
)

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

def _is_explainability_query(text: str) -> bool:
    lower = text.lower()
    return any(t in lower for t in _EXPLAINABILITY_TRIGGERS)

# Order card builder (Group 1)
def _build_order_card(tool_resp: dict) -> str:
    """Build a Markdown order status card from a get_order_status response."""
    if not tool_resp.get("found"):
        return ""
    return (
        f"| Field | Value |\n"
        f"|-------|-------|\n"
        f"| **Order ID** | {tool_resp.get('order_id', '—')} |\n"
        f"| **Product** | {tool_resp.get('product_name', '—')} |\n"
        f"| **Status** | {tool_resp.get('status', '—')} |\n"
        f"| **ETA** | {tool_resp.get('eta', '—')} |\n"
        f"| **Carrier** | {tool_resp.get('carrier', '—')} |"
    )

# Product card builder (Group 1)
def _build_product_card(tool_resp: dict) -> str:
    """Build a Markdown product card from a lookup_product response."""
    products = tool_resp.get("products", [])
    if not products:
        return ""
    lines = []
    for p in products[:3]:  # show up to 3 products
        lines.append(f"### {p.get('name', 'Product')}")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        lines.append(f"| **Price** | ${p.get('price', '—')} |")
        lines.append(f"| **Category** | {p.get('category', '—')} |")
        stock_qty = p.get('stock_qty', 0)
        in_stock = "✅ In Stock" if stock_qty > 0 else "❌ Out of Stock"
        lines.append(f"| **Availability** | {in_stock} ({stock_qty} units) |")
        lines.append(f"| **Description** | {p.get('description', '—')} |")
        lines.append("")
    return "\n".join(lines)

# Budget filter actions (Group 3)
def _build_budget_actions() -> list[cl.Action]:
    """Return budget-filter action buttons for product search results."""
    return [
        cl.Action(name="filter_budget",   value="budget",   label="💰 Budget (<$100)"),
        cl.Action(name="filter_midrange", value="mid-range", label="💼 Mid-range ($100–$500)"),
        cl.Action(name="filter_premium",  value="premium",  label="⭐ Premium (>$500)"),
    ]

# Explainability summary (Group 6)
async def _send_explainability() -> None:
    turn_log = cl.user_session.get("turn_log", [])
    if not turn_log:
        await cl.Message(
            content="No turns yet in this session. Ask me something first!"
        ).send()
        return

    last = turn_log[-1]
    lines = [
        "### How I answered that",
        f"**Agent:** {last.get('author', 'Orchestrator')}",
        f"**Route:** {last.get('route', '—')}",
        "",
        "**Tool calls:**",
    ]
    for tool in last.get("tools_called", []):
        lines.append(f"- `{tool}`")
    if not last.get("tools_called"):
        lines.append("- *(direct answer — no tools needed)*")

    guardrail_events = last.get("guardrail_events", [])
    if guardrail_events:
        lines.append("\n**Guardrail events:**")
        for ge in guardrail_events:
            lines.append(f"- `{ge.get('guardrail', '')}` → **{ge.get('action', '')}**: {ge.get('detail', '')}")

    await cl.Message(content="\n".join(lines)).send()

async def _send_admin_panel() -> None:
    """Show admin panel: session info, routing decisions, turn history."""
    turn_log = cl.user_session.get("turn_log", [])
    user_id = cl.user_session.get("user_id", "—")
    session_id = cl.user_session.get("session_id", "—")
    customer_name = cl.user_session.get("customer_name") or "unknown"

    lines = [
        "### 🔧 Admin Panel",
        f"**Session:** `{session_id}`",
        f"**User:** `{user_id}`",
        f"**Customer name:** {customer_name}",
        f"**Turns this session:** {len(turn_log)}",
        "",
        "**Last routing decisions:**",
    ]
    for entry in routing_log[-5:]:
        status = entry.get("status", "?")
        model = entry.get("model", "?").split("/")[-1]
        ms = entry.get("latency_ms", "")
        err = entry.get("error", "")
        suffix = f" — {err}" if err else f" ({ms} ms)" if ms else ""
        lines.append(f"- {status}: `{model}`{suffix}")
    if not routing_log:
        lines.append("- *(no routing events yet)*")

    if turn_log:
        lines.append("")
        lines.append("**Recent turns:**")
        for i, t in enumerate(turn_log[-5:], 1):
            route = t.get("route", "?")
            tools = ", ".join(t.get("tools_called", [])) or "none"
            snippet = t.get("prompt", "")[:60]
            lines.append(f"{i}. [{route}] `{snippet}` — tools: {tools}")

    langsmith_project = os.environ.get("LANGSMITH_PROJECT", "ecombot-capstone")
    lines.append("")
    lines.append(f"**LangSmith project:** `{langsmith_project}`")
    lines.append("")
    lines.append("*Type `/admin off` to exit admin mode, or any message to continue.*")

    await cl.Message(content="\n".join(lines)).send()
@cl.on_chat_start
async def on_chat_start():
    """Initialise per-session state and ADK runner."""
    runner, user_id, session_id = await make_runner(orchestrator)

    enable_routing_callbacks()  # wire LiteLLM callbacks for routing_log
    routing_log.clear()  # fresh log per session

    cl.user_session.set("runner", runner)
    cl.user_session.set("user_id", user_id)
    cl.user_session.set("session_id", session_id)
    cl.user_session.set("customer_name", None)     # Group 4
    cl.user_session.set("last_order_id", None)     # Group 4
    cl.user_session.set("last_product_name", None) # Group 4
    cl.user_session.set("turn_log", [])            # Group 6
    cl.user_session.set("turn_index", 0)
    cl.user_session.set("admin_mode", False)

    await cl.Message(
        content=(
            "Welcome to **eComBot** 🛒\n\n"
            "I can help you with:\n"
            "- **Order tracking** – check status, cancel, or get details\n"
            "- **Product discovery** – find, compare, and recommend products\n"
            "- **FAQ** – returns, shipping, warranty, and payment policies\n\n"
            "Type your question to get started!"
        )
    ).send()

# ADK runner + Chainlit step mapper
async def _run_turn(prompt: str) -> dict:
    """
    Send one turn to the Orchestrator and map ADK events to Chainlit Steps.

    Returns:
        text            — agent's final reply text
        author          — name of the agent that produced the reply
        tool_responses  — {tool_name: response_dict} for each tool called
        tools_called    — list of tool names in order
        has_error       — True if any tool returned an error dict
        guardrail_events — guardrail events recorded by guardrails.py
    """
    runner    = cl.user_session.get("runner")
    user_id   = cl.user_session.get("user_id")
    session_id = cl.user_session.get("session_id")

    open_steps: dict[str, cl.Step] = {}
    tool_responses: dict[str, dict] = {}
    tools_called: list[str] = []
    final_text = ""
    final_author = ""
    has_error = False

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:

                # Tool call → open a Step
                if fc := getattr(part, "function_call", None):
                    args = dict(fc.args or {})
                    label = _TOOL_LABELS.get(fc.name, fc.name.replace("_", " ").title())
                    step = cl.Step(name=label, type="tool")
                    step.input = json.dumps(args, indent=2)
                    await step.send()
                    open_steps[fc.name] = step
                    tools_called.append(fc.name)

                # Tool response → close the Step
                if fr := getattr(part, "function_response", None):
                    if fr.name in open_steps:
                        step = open_steps.pop(fr.name)
                        resp = fr.response or {}
                        is_err = isinstance(resp, dict) and "error" in resp
                        step.output = f"```json\n{json.dumps(resp, indent=2)}\n```"
                        step.is_error = is_err
                        if is_err:
                            has_error = True
                        tool_responses[fr.name] = resp
                        step.end = _utcnow()
                        await step.update()

        if event.is_final_response() and event.content and event.content.parts:
            text = event.content.parts[0].text
            if text:
                final_text = text
                final_author = event.author

    # Read guardrail events from session state
    guardrail_events: list[dict] = []
    try:
        session_service = runner.session_service
        sess = await session_service.get_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        if sess and sess.state:
            guardrail_events = list(sess.state.get("guardrail_events", []))
    except Exception:
        pass

    return {
        "text": final_text.strip(),
        "author": final_author,
        "tool_responses": tool_responses,
        "tools_called": tools_called,
        "has_error": has_error,
        "guardrail_events": guardrail_events,
    }

# Budget filter action handlers (Group 3)
@cl.action_callback("filter_budget")
async def filter_budget(action: cl.Action):
    await cl.Message(content="Looking for budget options under $100...").send()
    routing_log.clear()
    result = await _run_turn("Show me products under $100.")
    await _send_result(result)

@cl.action_callback("filter_midrange")
async def filter_midrange(action: cl.Action):
    await cl.Message(content="Looking for mid-range options ($100–$500)...").send()
    routing_log.clear()
    result = await _run_turn("Show me products between $100 and $500.")
    await _send_result(result)

@cl.action_callback("filter_premium")
async def filter_premium(action: cl.Action):
    await cl.Message(content="Looking for premium options over $500...").send()
    routing_log.clear()
    result = await _run_turn("Show me products over $500.")
    await _send_result(result)

# Result sender
async def _send_result(
    result: dict,
    *,
    model_used: str = "",
    rag_sources: list[str] | None = None,
) -> None:
    """Send the final text, any structured cards, guardrail indicators, and metadata footer."""
    final_text = result["text"]
    tool_responses = result["tool_responses"]
    guardrail_events = result["guardrail_events"]

    # Guardrail block indicator
    if guardrail_events:
        blocked = [e for e in guardrail_events if e.get("action") == "blocked"]
        sanitised = [e for e in guardrail_events if e.get("action") == "sanitised"]
        redacted = [e for e in guardrail_events if e.get("action") == "redacted"]
        if blocked:
            detail = blocked[-1].get("detail", "")
            await cl.Message(
                content=f"🛡️ **Request blocked by guardrail**\n\n*{detail}*"
            ).send()
            return
        if sanitised:
            detail = sanitised[-1].get("detail", "")
            await cl.Message(
                content=f"⚠️ *Part of the request was sanitised: {detail}*"
            ).send()
        if redacted:
            detail = redacted[-1].get("detail", "")
            await cl.Message(
                content=f"🔒 *Sensitive data was redacted from the response: {detail}*"
            ).send()

    # Group 1: Structured cards
    elements = []

    # Order card
    for tool_name in ("get_order_status", "get_order_status_mcp"):
        if tool_name in tool_responses:
            card_md = _build_order_card(tool_responses[tool_name])
            if card_md:
                elements.append(
                    cl.Text(name="Order Status", content=card_md, display="inline")
                )
                # Group 4: persist last order ID
                order_id = tool_responses[tool_name].get("order_id")
                if order_id:
                    cl.user_session.set("last_order_id", order_id)

    # Product card
    if "lookup_product" in tool_responses:
        card_md = _build_product_card(tool_responses["lookup_product"])
        if card_md:
            elements.append(
                cl.Text(name="Product Details", content=card_md, display="inline")
            )
            products = tool_responses["lookup_product"].get("products", [])
            if products:
                cl.user_session.set("last_product_name", products[0].get("name"))

    # Group 3: Budget filter buttons after product search
    actions = []
    if "lookup_product" in tool_responses:
        actions = _build_budget_actions()

    if final_text:
        # Append model badge + RAG source tag footer when available
        footer_parts = []
        if model_used:
            footer_parts.append(f"🤖 `{model_used}`")
        if rag_sources:
            footer_parts.append(f"📚 {', '.join(rag_sources)}")
        if footer_parts:
            final_text = final_text + "\n\n---\n*" + " · ".join(footer_parts) + "*"

        await cl.Message(content=final_text, elements=elements, actions=actions).send()
    elif result["has_error"]:
        await cl.Message(
            content="⚠️ One or more tools reported an error. Please check the steps above.",
            elements=elements,
        ).send()

# Message handler
@cl.on_message
async def on_message(message: cl.Message):
    prompt = message.content.strip()

    # Admin panel command
    if prompt.lower() in ("/admin", "/admin on"):
        cl.user_session.set("admin_mode", True)
        await _send_admin_panel()
        return
    if prompt.lower() == "/admin off":
        cl.user_session.set("admin_mode", False)
        await cl.Message(content="Admin mode disabled.").send()
        return
    if cl.user_session.get("admin_mode"):
        await _send_admin_panel()
        return

    # Group 6: Explainability
    if _is_explainability_query(prompt):
        await _send_explainability()
        return

    # Group 4: Update session context from prompt
    order_matches = _ORDER_RE.findall(prompt)
    if order_matches:
        cl.user_session.set("last_order_id", order_matches[-1].upper())

    # Clear per-turn routing log before the ADK turn so we capture only this turn's models
    routing_log.clear()

    # Run the ADK turn
    result = await _run_turn(prompt)
    runner = cl.user_session.get("runner")
    user_id = cl.user_session.get("user_id")
    session_id = cl.user_session.get("session_id")
    turn_idx = cl.user_session.get("turn_index", 0)

    # Extract model from routing_log (last successful call wins)
    model_used = ""
    for entry in reversed(routing_log):
        if entry.get("status") == "success":
            raw = entry.get("model", "")
            model_used = raw.split("/")[-1]  # e.g. "gemini-2.5-flash"
            break

    # RAG source tag: if query looks like a knowledge lookup, surface top sources
    rag_sources: list[str] = []
    try:
        route = classify_query(prompt)
        if route in ("fast-faq", "deep-support"):
            chunks = retrieve(prompt, n_results=2)
            seen: set[str] = set()
            for c in chunks:
                src = c.get("metadata", {}).get("source_file", "")
                name = os.path.basename(src) if src else ""
                if name and name not in seen:
                    rag_sources.append(name)
                    seen.add(name)
    except Exception:
        pass

    # Use run_turn from reasoning.py for the Sales agent path to get step narration
    reasoning_result: TurnResult | None = None
    if "delegate_to_sales" in result.get("tools_called", []) or not result["tools_called"]:
        try:
            reasoning_result = await _reasoning_run_turn(
                runner, user_id, session_id, prompt, turn_idx
            )
        except Exception:
            reasoning_result = None

    # Render reasoning steps
    if reasoning_result and reasoning_result.steps:
        for step in reasoning_result.steps:
            if step.kind in ("action", "observation"):
                async with cl.Step(name=f"{step.kind}: {step.label}", type="tool") as rs:
                    rs.input = step.detail
                    rs.output = step.detail[:200]

    # LangSmith trace (no-op if LANGSMITH_API_KEY not set)
    if reasoning_result:
        trace_turn(
            agent_name="ecombot_orchestrator",
            user_id=user_id,
            session_id=session_id,
            message=prompt,
            turn_result=reasoning_result,
            turn_index=turn_idx,
        )
    cl.user_session.set("turn_index", turn_idx + 1)

    # Group 4: persist customer name from save_customer_name tool response
    if "save_customer_name" in result["tool_responses"]:
        name_resp = result["tool_responses"]["save_customer_name"]
        if name_resp.get("saved"):
            cl.user_session.set("customer_name", name_resp.get("customer_name", ""))

    # Log the turn for explainability (Group 6)
    turn_log = cl.user_session.get("turn_log", [])
    turn_log.append({
        "prompt": prompt,
        "author": result["author"],
        "route": "support" if "delegate_to_support" in result["tools_called"]
                 else "sales" if "delegate_to_sales" in result["tools_called"]
                 else "direct",
        "tools_called": result["tools_called"],
        "guardrail_events": result["guardrail_events"],
        "model": model_used,
    })
    cl.user_session.set("turn_log", turn_log[-10:])  # keep last 10 turns

    await _send_result(result, model_used=model_used, rag_sources=rag_sources or None)
