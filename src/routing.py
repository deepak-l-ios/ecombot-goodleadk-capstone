"""
routing.py — LiteLLM routing and fallback configuration
========================================================
Routes eComBot queries by complexity and protects against provider failures
using litellm.Router.

Two model groups:
  fast-faq      → lighter model for FAQ and simple queries
                  (return policy, shipping info, order status)
  deep-support  → stronger model for complex multi-step flows
                  (product comparisons, multi-item complaints)
"""

import os

import litellm
from litellm import Router

# Model identifiers (single source of truth)
FAST_MODEL   = os.getenv("FAST_MODEL",   "openrouter/google/gemini-2.5-flash")   # fast FAQ
DEEP_MODEL   = os.getenv("DEEP_MODEL",   "openrouter/google/gemini-2.5-pro")     # deep support
BACKUP_MODEL = os.getenv("BACKUP_MODEL", "openrouter/openai/gpt-4o-mini")        # cross-provider fallback

# Routing event capture
# demo.py clears this list before each scenario and reads it afterwards
# to print the gateway routing decisions (model chosen, latency, errors).
routing_log: list[dict] = []

def _on_success(kwargs, completion_response, start_time, end_time) -> None:
    model = (
        kwargs.get("litellm_params", {}).get("model")
        or kwargs.get("model", "unknown")
    )
    ms = round((end_time - start_time).total_seconds() * 1000)
    routing_log.append({"status": "success", "model": model, "latency_ms": ms})

def _on_failure(kwargs, completion_response, start_time, end_time) -> None:
    model = (
        kwargs.get("litellm_params", {}).get("model")
        or kwargs.get("model", "unknown")
    )
    exc = kwargs.get("exception")
    routing_log.append({
        "status": "failure",
        "model": model,
        "error": type(exc).__name__ if exc else "unknown",
    })

def enable_routing_callbacks() -> None:
    """Attach routing event callbacks to litellm. Call once at startup."""
    if _on_success not in litellm.success_callback:
        litellm.success_callback.append(_on_success)
    if _on_failure not in litellm.failure_callback:
        litellm.failure_callback.append(_on_failure)

# Router factory
def _params(model: str, timeout: float = 30.0) -> dict:
    return {
        "model": model,
        "api_key": os.getenv("OPENROUTER_API_KEY"),
        "api_base": "https://openrouter.ai/api/v1",
        "timeout": timeout,
    }

def _make_router(
    primary: str,
    backup: str,
    *,
    primary_timeout: float = 30.0,
    num_retries: int = 0,
) -> Router:
    return Router(
        model_list=[
            {"model_name": "primary", "litellm_params": _params(primary, primary_timeout)},
            {"model_name": "backup",  "litellm_params": _params(backup)},
        ],
        fallbacks=[{"primary": ["backup"]}],
        num_retries=num_retries,
        retry_after=1,
        allowed_fails=1,
        cooldown_time=5,
    )

# Named routers
# Normal routing — ADK agents use their model strings directly.
faq_router     = _make_router(FAST_MODEL,  BACKUP_MODEL)
support_router = _make_router(DEEP_MODEL,  BACKUP_MODEL)

# Fallback demo: primary model name does not exist → provider error → fallback
fallback_demo_router = _make_router(
    primary="openrouter/google/bad-model-xyz",
    backup=BACKUP_MODEL,
    num_retries=1,
)

# Timeout demo: near-zero timeout on primary → Timeout exception → fallback
timeout_demo_router = _make_router(
    primary=DEEP_MODEL,
    backup=BACKUP_MODEL,
    primary_timeout=0.001,   # guaranteed timeout — shows fallback reliably
    num_retries=0,
)

# Query classifier: maps eComBot queries to route hints.
# The route hint selects the right ADK agent in demo.py.

_FAQ_KEYWORDS = {
    "return", "returns", "refund", "warranty", "shipping", "delivery",
    "policy", "guarantee", "exchange", "days", "how long", "how do i",
    "what is", "payment", "accepted", "cod", "emi", "cancel",
}

_SUPPORT_KEYWORDS = {
    "compare", "comparison", "recommend", "recommend me", "best", "versus",
    "vs", "difference", "pros and cons", "upgrade", "budget", "under",
    "features", "specs", "specification", "which one", "help me choose",
    "complex", "multiple", "several",
}

def classify_query(query: str) -> str:
    """
    Classify an eComBot query as 'fast-faq' or 'deep-support'.

    Returns:
        'fast-faq'     — lightweight FAQ or simple status question
        'deep-support' — complex multi-step or reasoning-heavy question
    """
    lower = query.lower()
    support_hits = sum(1 for kw in _SUPPORT_KEYWORDS if kw in lower)
    faq_hits     = sum(1 for kw in _FAQ_KEYWORDS if kw in lower)

    if support_hits > faq_hits:
        return "deep-support"
    return "fast-faq"
