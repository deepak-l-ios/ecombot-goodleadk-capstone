"""
support_agent.py — eComBot Support Agent
=========================================
Defines the support agent with full tool set, RAG grounding, LiteLLM routing,
and FastMCP servers.

Session management lives in session.py (project root).
Tool logic lives in tools/order_tools.py and tools/product_tools.py.
RAG logic lives in rag/embed_catalog.py and rag/retriever.py.
Routing config lives in routing.py.
MCP servers live in services/mcp_servers/.
"""

import atexit
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import litellm
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import (
    McpToolset,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)

# Silence noisy loggers
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
os.environ.setdefault("LITELLM_LOG", "ERROR")
for _name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.CRITICAL)
    _log.propagate = False

litellm.suppress_debug_info = True
load_dotenv()

from tools.order_tools import cancel_order, get_order_status, save_customer_name
from tools.product_tools import lookup_product
from rag.retriever import retrieve
from routing import FAST_MODEL, DEEP_MODEL
from guardrails import output_pii_guardrail, tool_safety_guardrail

# Model
_MODEL = "openrouter/google/gemini-2.5-flash"

# MCP server paths and connection config
_SERVICES_DIR = Path(__file__).parent.parent / "services" / "mcp_servers"
_ORDERS_SERVER = str(_SERVICES_DIR / "orders_server.py")
_INVENTORY_SERVER = str(_SERVICES_DIR / "inventory_server.py")

_ORDERS_HOST = os.getenv("ORDERS_SERVER_HOST", "127.0.0.1")
_ORDERS_PORT = int(os.getenv("ORDERS_SERVER_PORT", "8766"))
_ORDERS_URL  = f"http://{_ORDERS_HOST}:{_ORDERS_PORT}/mcp"

_SLOW_INVENTORY_DELAY   = os.getenv("INVENTORY_SEARCH_DELAY_SECONDS", "0")
_SLOW_INVENTORY_TIMEOUT = float(os.getenv("INVENTORY_TOOL_TIMEOUT_SECONDS", "5"))

def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    """Block until the TCP port is accepting connections or raise RuntimeError."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(
        f"orders_server.py did not start on {host}:{port} within {timeout}s"
    )

def _start_orders_server() -> subprocess.Popen:
    """Start the orders MCP server as a background process."""
    proc = subprocess.Popen(
        [sys.executable, _ORDERS_SERVER],
        env={
            **os.environ,
            "ORDERS_SERVER_HOST": _ORDERS_HOST,
            "ORDERS_SERVER_PORT": str(_ORDERS_PORT),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_port(_ORDERS_HOST, _ORDERS_PORT)
    return proc

def _shutdown_orders_server() -> None:
    """Terminate the background orders MCP server. Safe to call more than once."""
    if _orders_server_process.poll() is None:
        _orders_server_process.terminate()
        _orders_server_process.wait(timeout=5)

# Start the orders MCP server as a background process when this module is imported.
# This is the same pattern as lab/demo/day08/agent.py.
_orders_server_process = _start_orders_server()
atexit.register(_shutdown_orders_server)

def _orders_toolset() -> McpToolset:
    """McpToolset connected to the orders Streamable HTTP MCP server."""
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=_ORDERS_URL,
            timeout=10,
        ),
    )

def _inventory_toolset(*, delay_seconds: str = "0", timeout: float = 5.0) -> McpToolset:
    """McpToolset that spawns the inventory stdio MCP server as a subprocess."""
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params={
                "command": sys.executable,
                "args": [_INVENTORY_SERVER],
                "env": {
                    **os.environ,
                    "INVENTORY_SEARCH_DELAY_SECONDS": delay_seconds,
                },
            },
            timeout=timeout,
        ),
    )
_RAG_TOP_K = 3

# Base persona
_PERSONA = """
You are eComBot, a professional support agent for an electronics e-commerce store.

Your capabilities:
- Save the customer's name using the save_customer_name tool when they introduce themselves.
- Check order status using the get_order_status tool.
- Cancel an order using the cancel_order tool.
- Look up product information using the lookup_product tool.
- Answer product knowledge, FAQ, warranty, shipping, and returns questions using the retrieved knowledge base context below.

Guidelines:
- Call save_customer_name as soon as the customer shares their name.
- Use the customer's name in every reply once it is known.
- Always call the appropriate tool when the user asks about an order or product by ID.
  Do NOT guess or invent order statuses, ETAs, prices, or inventory.
- Ask for the order ID (format: ORD-XXX) if it is missing before calling a tool.
- After looking up an order, remember the order ID and customer name for follow-ups.
  Do not ask the customer to repeat information already stored in the session.
- After looking up a product, remember it for follow-up questions about price or availability.
- If a tool returns an error, relay the message clearly. Do not expose stack traces.
- If asked about something outside e-commerce (e.g. writing code), politely decline
  and offer to help with orders or products instead.
- Keep responses concise, clear, and customer-friendly.
""".strip()

# Grounding rules (hallucination guard)
_GROUNDING_RULES = """
Knowledge base grounding rules:
- When the "Retrieved knowledge base context" section below contains relevant information,
  use it as your primary source. Do not contradict retrieved evidence.
- If the retrieved context does not contain enough information to answer the question,
  say clearly: "I don't have that information in our current knowledge base. Please
  contact our support team for further help."
- Never invent product specifications, pricing, warranty terms, shipping timelines,
  or return policies that are not in the retrieved context or confirmed by a tool call.
- You may still use tool calls (get_order_status, cancel_order, lookup_product) for
  live order and product data — these take priority over static knowledge base content.
""".strip()

# InstructionProvider
def _format_context(results: list[dict]) -> str:
    """Render retrieved chunks (or their absence) for the instruction."""
    if not results:
        return (
            "Retrieved knowledge base context: NOTHING RELEVANT FOUND.\n"
            "Apply the fallback grounding rule: if the user is asking a knowledge "
            "question (not an order/product tool call), say you don't have that "
            "information in the current knowledge base."
        )
    lines = ["Retrieved knowledge base context (ground your answer in this):"]
    for r in results:
        source = r["metadata"].get("source_file", "")
        section = r["metadata"].get("section", "")
        page = r["metadata"].get("page", "")
        citation_parts = [p for p in [source, section, f"p.{page}" if page else ""] if p]
        citation = f"  [{', '.join(citation_parts)}]" if citation_parts else ""
        lines.append(f"- (similarity={r['score']:.2f}){citation}\n  {r['text']}")
    return "\n".join(lines)

def _build_instruction(ctx: ReadonlyContext) -> str:
    """
    InstructionProvider: runs once per turn before the model is called.

    Extracts the latest user message, retrieves the most relevant knowledge
    base chunks for it, and appends them — plus grounding rules — to the
    persona so the model answers from retrieved evidence rather than its
    own training data.
    """
    query = ""
    if ctx.user_content and ctx.user_content.parts:
        query = "".join(
            part.text or ""
            for part in ctx.user_content.parts
            if part.text
        )

    results = retrieve(query, n_results=_RAG_TOP_K) if query.strip() else []
    context_block = _format_context(results)
    return f"{_PERSONA}\n\n{_GROUNDING_RULES}\n\n{context_block}"

# Agent
# Fast route — FAQ and simple order-status queries.
fast_support_agent = LlmAgent(
    name="ecombot_support_fast",
    model=LiteLlm(model=FAST_MODEL),
    instruction=_build_instruction,
    description=(
        "eComBot support agent (fast-faq route): simple order status, "
        "straightforward FAQ answers grounded in the knowledge base."
    ),
    tools=[save_customer_name, get_order_status, cancel_order, lookup_product],
    after_model_callback=output_pii_guardrail,
    before_tool_callback=tool_safety_guardrail,
)

# Deep route — complex product comparisons and multi-step flows.
deep_support_agent = LlmAgent(
    name="ecombot_support_deep",
    model=LiteLlm(model=DEEP_MODEL),
    instruction=_build_instruction,
    description=(
        "eComBot support agent (deep-support route): complex product comparisons, "
        "multi-step reasoning, and high-stakes support flows."
    ),
    tools=[save_customer_name, get_order_status, cancel_order, lookup_product],
    after_model_callback=output_pii_guardrail,
    before_tool_callback=tool_safety_guardrail,
)

# MCP-enabled agent — orders + inventory via FastMCP servers.
mcp_support_agent = LlmAgent(
    name="ecombot_support_mcp",
    model=LiteLlm(model=DEEP_MODEL),
    instruction=_build_instruction,
    description=(
        "eComBot support agent (MCP route): order management and inventory "
        "checks via FastMCP servers; RAG grounding for FAQ."
    ),
    tools=[
        save_customer_name,
        lookup_product,
        _orders_toolset(),
        _inventory_toolset(
            delay_seconds=_SLOW_INVENTORY_DELAY,
            timeout=_SLOW_INVENTORY_TIMEOUT,
        ),
    ],
    after_model_callback=output_pii_guardrail,
    before_tool_callback=tool_safety_guardrail,
)

# Compatibility alias.
support_agent = LlmAgent(
    name="ecombot_support",
    model=LiteLlm(model=_MODEL),
    instruction=_build_instruction,
    description=(
        "eComBot support agent: order status, order cancellation, "
        "product lookup, knowledge-base grounded FAQ answers, "
        "and multi-turn session context."
    ),
    tools=[save_customer_name, get_order_status, cancel_order, lookup_product],
    after_model_callback=output_pii_guardrail,
    before_tool_callback=tool_safety_guardrail,
)

