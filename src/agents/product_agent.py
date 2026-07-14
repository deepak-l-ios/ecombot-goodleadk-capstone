"""
product_agent.py — eComBot Product Discovery Agent
====================================================
Instruction-only agent for product discovery and catalog browsing.
Swap the instruction to compare tone, scope, and behavior.
"""

import logging
import os

import litellm
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

logging.getLogger("asyncio").setLevel(logging.CRITICAL)
os.environ.setdefault("LITELLM_LOG", "ERROR")
for _name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.CRITICAL)
    _log.propagate = False

litellm.suppress_debug_info = True
load_dotenv()

_MODEL = "openrouter/google/gemini-2.5-flash"

_INSTRUCTION = """
You are eComBot Product Assistant, a specialist in electronics product discovery.

Your role:
- Help customers find the right product for their needs.
- Answer questions about product features, compatibility, and categories.
- Compare products when asked (based on general knowledge only).
- Guide customers toward the right purchase decision.

Guidelines:
- Do NOT quote live prices or real-time inventory — you do not have live data.
- If a product lookup tool becomes available, use it instead of guessing.
- Stay focused on electronics and e-commerce product topics.
- If asked about order status or account issues, direct the customer to support.
- Keep responses helpful, clear, and concise.
""".strip()

product_agent = LlmAgent(
    name="ecombot_product",
    model=LiteLlm(model=_MODEL),
    instruction=_INSTRUCTION,
    description="eComBot product discovery agent: helps customers find and compare electronics products.",
)
