"""
guardrails.py — eComBot ADK guardrails
========================================
Three independent layers, each a standard ADK callback:

  1. INPUT guardrail  → before_model_callback
        Catches prompt injection and policy-bypass attempts in the user's
        message and sanitises them before the model sees them. If nothing
        safe remains, it blocks.

  2. OUTPUT guardrail  → after_model_callback
        Scans the model's answer for PII (email / phone / account id) and
        redacts it before it reaches the user.

  3. TOOL guardrail    → before_tool_callback
        Validates tool arguments before the tool runs: rejects unsafe values
        (e.g. order_id=all), validates ORD-XXX format, and forces
        confirmation for destructive actions.

Each guardrail records what it did into session state under "guardrail_events"
so the Chainlit UI can show a clear "intercepted" indicator.
"""

import re
from typing import Callable, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

# Pattern banks
INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior|earlier|above) instructions",
    r"disregard (all )?(previous|prior|earlier|above) (instructions|prompts)",
    r"system prompt",
    r"reveal (your )?(instructions|system prompt|prompt|rules)",
    r"show me your (system )?(prompt|instructions)",
    r"internal policy",
    r"developer (message|prompt)",
    r"you are now",
    r"new persona",
]

SCOPE_PATTERNS = [
    r"bypass .*(policy|policies|rules|restrictions)",
    r"(reveal|show|leak) .*(admin|private|confidential|internal) (notes|data|info)",
    r"admin notes",
    r"override .*(policy|safety|guardrail)",
]

_PII = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"\+?\d[\d\s().-]{7,}\d"),
    "account id": re.compile(r"\b(?:ACC|ACCT|ACC-)[\s#:-]*\d{3,}\b", re.I),
}

# Competitor brand names — redacted from model output
_COMPETITOR_BRANDS = re.compile(
    r"\b(amazon|flipkart|snapdeal|meesho|myntra|alibaba|aliexpress|ebay|"
    r"walmart|best\s?buy|newegg|shopify|tatacliq|jiomart)\b",
    re.I,
)

# Off-topic subject patterns for output flagging
_OFF_TOPIC_OUTPUT = re.compile(
    r"\b(cryptocurrency|bitcoin|ethereum|nft|stock\s?market|"
    r"medical\s?advice|casino|gambling|betting|prescription|drug\s?dosage)\b",
    re.I,
)

_CLAUSE_SPLIT = re.compile(r"([.!?;\n,]+)")

# Connective fragments left behind after a clause is removed ("Also, …")
_ORPHAN = re.compile(
    r"^(also|and|but|or|so|then|still|please|if you can'?t do that|"
    r"and don'?t ask me again|don'?t ask me again)$",
    re.I,
)

# State helper
def _record(state, guardrail: str, action: str, detail: str) -> None:
    """Append a guardrail event to session state. De-duplicates identical events."""
    events = list(state.get("guardrail_events", []))
    record = {"guardrail": guardrail, "action": action, "detail": detail}
    if record in events:
        return
    events.append(record)
    state["guardrail_events"] = events

def _matches(text: str, patterns: list[str]) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.I)]

def _sanitise(text: str, patterns: list[str]) -> tuple[str, list[str]]:
    """Drop clauses matching any pattern; return (cleaned_text, removed_clauses)."""
    tokens = _CLAUSE_SPLIT.split(text)
    kept, removed = [], []
    i = 0
    while i < len(tokens):
        clause = tokens[i]
        delim = tokens[i + 1] if i + 1 < len(tokens) else ""
        stripped = clause.strip()
        if stripped and _matches(clause, patterns):
            removed.append(stripped)
        elif stripped and _ORPHAN.match(stripped):
            pass  # leftover connective — drop silently
        else:
            kept.append(clause + delim)
        i += 2
    return "".join(kept).strip(), removed

# 1. INPUT guardrail (before_model_callback)
def make_input_guardrail(label: str, patterns: list[str]) -> Callable:
    """Build a before_model_callback that sanitises matching clauses."""

    def guardrail(
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> Optional[LlmResponse]:
        removed_all: list[str] = []
        last_user_emptied = False

        for content in llm_request.contents or []:
            if content.role != "user" or not content.parts:
                continue
            for part in content.parts:
                if not getattr(part, "text", None):
                    continue
                cleaned, removed = _sanitise(part.text, patterns)
                if removed:
                    removed_all.extend(removed)
                    part.text = cleaned or "[request removed by guardrail]"
                    last_user_emptied = not cleaned

        if not removed_all:
            return None  # nothing to sanitise — let the model run normally

        if last_user_emptied:
            _record(
                callback_context.state, label, "blocked",
                f"entire request matched {label}; nothing safe to forward",
            )
            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=(
                        "I can't help with that request. I'm here to help you "
                        "with orders, products, and e-commerce queries."
                    ))],
                )
            )

        _record(
            callback_context.state, label, "sanitised",
            f"removed {len(removed_all)} clause(s): {removed_all}",
        )
        return None  # proceed with the cleaned request

    return guardrail

# Ready-made instances attached to agents.
injection_guardrail = make_input_guardrail("input:injection", INJECTION_PATTERNS)
scope_guardrail = make_input_guardrail("input:scope", SCOPE_PATTERNS)

# 2. OUTPUT guardrail (after_model_callback) — PII, competitor brand, and off-topic filter
def output_pii_guardrail(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Redact PII and competitor brand mentions from the model's reply.
    Flags off-topic content in guardrail_events without altering the text.
    """
    if getattr(llm_response, "partial", False):
        return None
    if not llm_response.content or not llm_response.content.parts:
        return None

    found_pii: list[str] = []
    found_competitors: list[str] = []
    found_offtopic: list[str] = []
    changed = False

    for part in llm_response.content.parts:
        text = getattr(part, "text", None)
        if not text:
            continue
        new_text = text

        # PII redaction
        for kind, rx in _PII.items():
            if rx.search(new_text):
                found_pii.append(kind)
                new_text = rx.sub(f"[REDACTED {kind.upper()}]", new_text)

        # Competitor brand redaction
        comp_matches = _COMPETITOR_BRANDS.findall(new_text)
        if comp_matches:
            found_competitors = [m.lower() for m in comp_matches]
            new_text = _COMPETITOR_BRANDS.sub("[COMPETITOR]", new_text)

        # Off-topic detection (flag only — do not alter text)
        ot_matches = _OFF_TOPIC_OUTPUT.findall(new_text)
        if ot_matches:
            found_offtopic = [m.lower() for m in ot_matches]

        if new_text != text:
            part.text = new_text
            changed = True

    if found_pii:
        _record(
            callback_context.state, "output:pii", "redacted",
            f"masked: {sorted(set(found_pii))}",
        )
    if found_competitors:
        _record(
            callback_context.state, "output:competitor", "redacted",
            f"brands removed: {sorted(set(found_competitors))}",
        )
    if found_offtopic:
        _record(
            callback_context.state, "output:off_topic", "flagged",
            f"off-topic terms detected: {sorted(set(found_offtopic))}",
        )

    if not changed and not found_offtopic:
        return None

    return llm_response if changed else None

# 3. TOOL guardrail (before_tool_callback) — argument safety
# Valid eComBot order ID format: ORD-XXX (XXX = 1-6 digits)
_VALID_ORDER_ID = re.compile(r"^ORD-\d{1,6}$", re.IGNORECASE)

# Tools that change or delete data and require confirmation
_DESTRUCTIVE_TOOLS = {"cancel_order", "cancel_order_mcp"}

def tool_safety_guardrail(
    tool: BaseTool,
    args: dict,
    tool_context: ToolContext,
) -> Optional[dict]:
    """
    Validate tool arguments before a tool call:
    - Reject malformed order IDs (format check: ORD-XXX).
    - Block bulk / wildcard identifiers (e.g. order_id="all").
    - Require explicit confirmation (via session state) for destructive tools.
    """
    if tool.name in _DESTRUCTIVE_TOOLS:
        order_id = str(args.get("order_id", "")).strip()

        # Format validation
        if not _VALID_ORDER_ID.match(order_id):
            _record(
                tool_context.state, f"tool:{tool.name}", "blocked",
                f"invalid order_id '{order_id}' rejected before tool call; "
                "expected format: ORD-XXX",
            )
            return {
                "status": "blocked",
                "reason": (
                    f"'{order_id}' is not a valid order ID. "
                    "Order IDs must match the format ORD-XXX (e.g. ORD-001)."
                ),
            }

        # Confirmation check — model-supplied confirmed=True is not trusted.
        # Confirmation must be tracked in session state across turns.
        confirm_key = f"cancel_confirmed_{order_id.upper()}"
        if not tool_context.state.get(confirm_key):
            tool_context.state[confirm_key] = "pending"
            _record(
                tool_context.state, f"tool:{tool.name}",
                "confirmation_required",
                f"destructive cancel of {order_id} blocked pending user confirmation",
            )
            return {
                "status": "confirmation_required",
                "order_id": order_id,
                "message": (
                    f"Please confirm: cancel order {order_id}? "
                    "This action cannot be undone. "
                    "Reply 'yes, cancel ORD-XXX' to proceed."
                ),
            }

    return None  # safe — allow the tool to run
