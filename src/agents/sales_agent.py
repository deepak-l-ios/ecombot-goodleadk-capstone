"""
sales_agent.py — eComBot Sales Agent
======================================
Product discovery, comparisons, and budget-constrained recommendations
using lookup_product tool and RAG grounding. Uses a ReAct reasoning loop
for multi-step recommendation flows.
"""

import logging
import os

import litellm
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.lite_llm import LiteLlm

logging.getLogger("asyncio").setLevel(logging.CRITICAL)
os.environ.setdefault("LITELLM_LOG", "ERROR")
for _name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.CRITICAL)
    _log.propagate = False

litellm.suppress_debug_info = True
load_dotenv()

from tools.product_tools import lookup_product
from rag.retriever import retrieve
from routing import DEEP_MODEL

_MODEL = DEEP_MODEL  # Sales agent uses the capable model for reasoning

_RAG_TOP_K = 3

# Base persona
_PERSONA = """
You are eComBot Sales Assistant, the product discovery and recommendation
specialist for our electronics e-commerce store.

Your capabilities:
- Find products using the lookup_product tool (search by name, category, or keywords).
- Recommend products based on budget, use case, and customer preferences.
- Compare multiple products side-by-side on key specs, price, and value.
- Help customers choose between models in the same category.

Guidelines:
- Always call lookup_product to find real products before recommending anything.
  Never invent product names, prices, or specifications that are not confirmed
  by a tool call or retrieved knowledge base context.
- For budget queries: search by category first (e.g. "audio", "television"),
  then filter results by the stated budget. If nothing fits, say so clearly.
- For comparisons: look up each product individually, then compare them using
  the retrieved specs. Highlight trade-offs (price vs features, battery vs quality).
- For vague requests ("best phone under ₹20k"): ask ONE clarifying question
  about use case before searching.
- If the customer rejects a recommendation, acknowledge what constraint changed
  (price, feature, size) and search again with the corrected constraint.
  Do NOT repeat the same recommendation.
- If the customer has an order problem or support issue, tell them: "This looks
  like a support question — let me route you to our Support team."
- Stay within the electronics e-commerce domain. Politely decline off-topic requests.
""".strip()

# Grounding rules (hallucination guard)
_GROUNDING_RULES = """
Knowledge base grounding rules:
- When the "Retrieved knowledge base context" section below contains relevant
  product specifications, warranty info, or FAQ answers, use it as your primary
  source. Do not contradict retrieved evidence.
- Never invent product specs, warranty terms, prices, or availability data
  not present in retrieved context or confirmed by a tool call.
- If retrieved context is insufficient, say: "I don't have full details on that
  in our knowledge base. Let me search our product catalog instead."
""".strip()

# ReAct reasoning rules
_REACT_RULES = """
Reasoning loop for recommendations:
1. Extract constraints from the user's request (budget, category, features, use case).
2. Call lookup_product to search the catalog — use the category or product name.
3. From the results, filter by budget and feature requirements.
4. If nothing matches: broaden the search (relax one constraint) and explain the trade-off.
5. Present the best 1-2 options with a short rationale. Stop after 3 search attempts.
6. If the user rejects a recommendation:
   - Identify what constraint failed ("too expensive", "wrong category", etc.).
   - Re-run the reasoning loop with the corrected constraint.
   - Begin your reply with: "Got it — let me adjust my search."
""".strip()

def _format_context(results: list[dict]) -> str:
    """Render retrieved chunks (or their absence) for the instruction."""
    if not results:
        return (
            "Retrieved knowledge base context: NOTHING RELEVANT FOUND.\n"
            "If the user is asking about specs or features, call lookup_product first."
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
    InstructionProvider: retrieve relevant knowledge base chunks before each
    turn so the agent answers from retrieved evidence rather than training data.
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
    return f"{_PERSONA}\n\n{_GROUNDING_RULES}\n\n{_REACT_RULES}\n\n{context_block}"

# Agent
sales_agent = LlmAgent(
    name="ecombot_sales",
    model=LiteLlm(model=_MODEL),
    instruction=_build_instruction,
    description=(
        "eComBot sales agent: product discovery, budget-constrained "
        "recommendations, multi-product comparisons, and ReAct reasoning."
    ),
    tools=[lookup_product],
)
