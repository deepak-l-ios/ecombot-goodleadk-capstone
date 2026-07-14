"""
demo.py — eComBot Capstone: Interactive Support Agent Demo
===========================================================
Google ADK · LiteLLM · OpenRouter

Runs a scripted 6-turn scenario that covers the core Day01-Day04 flows,
then drops into a free REPL so you can explore further.
Type  q  to quit.

Run (in-memory, no persistence):
    SESSION_BACKEND=memory python demo.py

Run (full persistence):
    docker compose up -d
    SESSION_BACKEND=database python demo.py

Skip scenarios, go straight to REPL:
    python demo.py --repl
"""

import asyncio
import logging
import os
import sys
import textwrap

from dotenv import load_dotenv
from google.genai import types

load_dotenv()

# Ensure src/ is on sys.path
_SRC = os.path.join(os.path.dirname(__file__), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Silence LiteLLM noise
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
os.environ.setdefault("LITELLM_LOG", "ERROR")
for _name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
    _log = logging.getLogger(_name)
    _log.setLevel(logging.CRITICAL)
    _log.propagate = False

log = logging.getLogger("ecombot")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from agents.support_agent import support_agent, fast_support_agent, deep_support_agent
from agents.orchestrator import orchestrator, delegation_trace
from agents.sub_agent_patterns import (
    concierge_agent,
    order_assist_pipeline,
    product_research_pipeline,
)
from session import make_runner
from routing import classify_query, routing_log, enable_routing_callbacks

# Conditional database imports
_BACKEND = os.getenv("SESSION_BACKEND", "memory").lower()
_DB_MODE = _BACKEND in ("database", "redis")

if _DB_MODE:
    from services.db import check_connection as pg_ok
    from services.history_service import get_history, record_turn
    from services.session_service import (
        check_connection as redis_ok,
        load_session_ref,
        save_session_ref,
        save_session_state,
    )

def _pick_agent(query: str):
    """Return the appropriate agent based on query complexity."""
    route = classify_query(query)
    if route == "deep-support":
        return deep_support_agent, route
    return fast_support_agent, route

_GUIDE = """
  SCENARIO GUIDE — eComBot Capstone
  ────────────────────────────────────────────────────────────────────────
  Support scenarios (1-6):
  1  Greeting + name    "Hi, my name is Priya."
  2  Order lookup       "Where is my order ORD-001?"
  3  Follow-up (state)  "What is the carrier?"
  4  Product lookup     "Tell me about the 4K Smart TV."
  5  Order cancellation "Cancel order ORD-002."
  6  Already cancelled  "Cancel ORD-004."

  Routing scenarios (7-8):
  7  FAQ query          "What is your return policy?"
  8  Complex query      "Compare your 4K TV vs 8K TV for me."

  Multi-agent scenarios (9-12):
  9  Support route      "Where is ORD-001? I'm Priya."
  10 Sales route        "Recommend a noise-cancelling headphone under $200."
  11 Mixed intent       "My ORD-002 arrived damaged. Can you suggest a replacement TV?"
  12 Direct greeting    "Hi, what can you help me with?"

  Native ADK patterns (A1-C1):
  A1 Concierge → Product   concierge_agent routes product question to product_discovery_agent
  A2 Peer handoff           specialist-to-specialist handoff
  A3 Direct answer          concierge answers a general greeting itself
  B1 Sequential pipeline    order_assist_pipeline: lookup → recommend → recap
  C1 Parallel synthesis     product_research_pipeline: [specs | alternatives] → comparison
  ────────────────────────────────────────────────────────────────────────
  Scenarios 1-12 run in ONE session — context accumulates.
  ADK pattern demos run in separate fresh sessions.
"""

# Console helpers
def _wrap(text: str) -> str:
    prefix = "    "
    return textwrap.fill(text, width=74, initial_indent=prefix, subsequent_indent=prefix)

def _sep(char: str = "─", width: int = 70) -> None:
    print(f"  {char * width}")

def _build_message(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=text)])

# ADK ask helper
async def _ask(
    runner,
    user_id: str,
    session_id: str,
    prompt: str,
    *,
    record: bool = True,
) -> str:
    """
    Send a prompt to the agent and return its reply.
    When SESSION_BACKEND=database, records turns to PostgreSQL history and
    snapshots session state to Redis after each exchange.
    """
    reply = ""
    tool_events: list[dict] = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=_build_message(prompt),
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                reply = event.content.parts[0].text or ""
        # Capture tool call names for history
        if hasattr(event, "tool_calls") and event.tool_calls:
            for tc in event.tool_calls:
                tool_events.append({"tool": tc.name, "input": str(tc.args)})

    reply = reply.strip()

    if _DB_MODE and record:
        record_turn(session_id, user_id, "user", prompt)
        record_turn(session_id, user_id, "model", reply, tool_calls=tool_events or None)
        # Snapshot session state to Redis
        try:
            session_service = runner.session_service
            sess = await session_service.get_session(
                app_name=runner.app_name, user_id=user_id, session_id=session_id
            )
            if sess and sess.state:
                save_session_state(session_id, dict(sess.state))
        except Exception as exc:
            log.warning("State snapshot failed (non-fatal): %s", exc)

    return reply

# Scripted scenarios
_SCENARIOS = [
    ("1  Greeting + name",    "Hi, my name is Priya."),
    ("2  Order lookup",       "Where is my order ORD-001?"),
    ("3  Follow-up (state)",  "What is the carrier for that order?"),
    ("4  Product lookup",     "Tell me about the 4K Smart TV."),
    ("5  Order cancellation", "Cancel order ORD-002."),
    ("6  Already cancelled",  "Cancel ORD-004."),
    ("7  FAQ (fast-faq route)",         "What is your return policy?"),
    ("8  Complex (deep-support route)", "Compare the 4K Smart TV and the 8K OLED TV for a home theatre setup."),
    ("9   Support route (orchestrator)",   "Where is ORD-001? My name is Priya."),
    ("10  Sales route (orchestrator)",     "Recommend a noise-cancelling headphone under $200."),
    ("11  Mixed intent (orchestrator)",    "My ORD-002 arrived damaged. Can you suggest a replacement TV?"),
    ("12  Direct answer (orchestrator)",   "Hi, what can you help me with?"),
]

async def run_scenarios(runner, user_id: str, session_id: str) -> None:
    for label, prompt in _SCENARIOS:
        _sep()
        print(f"\n  [{label}]")
        print(f"\n  You: {prompt}")
                routing_log.clear()
        delegation_trace.clear()
        reply = await _ask(runner, user_id, session_id, prompt)
        route = classify_query(prompt)
        print(f"\n  [eComBot] (route: {route})\n{_wrap(reply)}\n")
        if routing_log:
            for entry in routing_log:
                status = entry.get("status", "?")
                model  = entry.get("model", "?").split("/")[-1]
                ms     = entry.get("latency_ms", "?")
                err    = entry.get("error", "")
                suffix = f" ← {err}" if err else f" ({ms} ms)"
                print(f"  [routing] {status:7}  {model}{suffix}")
                if delegation_trace:
            print()
            for entry in delegation_trace:
                if entry["type"] == "call":
                    print(f"  [delegate→{entry['agent']}] call  {entry['tool']}({entry['args']})")
                else:
                    status_str = str(entry.get("response", {}))[:60]
                    print(f"  [delegate→{entry['agent']}] result {entry['tool']} → {status_str}")

    _sep("=")

    # Print history from PostgreSQL
    if _DB_MODE:
        print("\n  [Session History from PostgreSQL]")
        _sep()
        for turn in get_history(session_id):
            ts = str(turn.get("created_at", ""))[:19]
            print(f"  {turn['role'].upper():6}  {ts}  {str(turn['content'])[:80]}")
        _sep()

async def run_day09a_demos() -> None:
    """Demonstrate native ADK sub_agents + Workflow patterns."""
    print("\n" + "=" * 72)
    print("  Native ADK Multi-Agent Patterns")
    print("=" * 72)

    # ── Pattern A: sub_agents routing ──────────────────────────────────────
    print("\n  [Pattern A] Agent routing via sub_agents + transfer_to_agent")
    _sep()
    concierge_runner, uid, sid = await make_runner(concierge_agent)

    a_scenarios = [
        ("A1  Concierge → Product",    "Can you tell me about the Noise-Cancelling Headphones XB500?"),
        ("A2  Peer handoff",           "What's the status of my order ORD-001?"),
        ("A3  Direct answer",          "Hi! What can eComBot help me with?"),
    ]
    for label, prompt in a_scenarios:
        _sep()
        print(f"\n  [{label}]")
        print(f"\n  You: {prompt}")
        reply = await _ask(concierge_runner, uid, sid, prompt, record=False)
        print(f"\n  [eComBot]\n{_wrap(reply)}\n")

    # ── Pattern B: Sequential Workflow ─────────────────────────────────────
    print("\n  [Pattern B] Sequential Workflow: order_lookup → recommend → recap")
    _sep()
    pipeline_runner, uid_b, sid_b = await make_runner(order_assist_pipeline)
    prompt_b = "Check ORD-001 and suggest something I might also like."
    print(f"\n  You: {prompt_b}")
    reply_b = await _ask(pipeline_runner, uid_b, sid_b, prompt_b, record=False)
    print(f"\n  [eComBot pipeline]\n{_wrap(reply_b)}\n")

    # ── Pattern C: Parallel + fan-in Workflow ──────────────────────────────
    print("\n  [Pattern C] Parallel Workflow: [specs | alternatives] → comparison")
    _sep()
    research_runner, uid_c, sid_c = await make_runner(product_research_pipeline)
    prompt_c = "Research the Noise-Cancelling Headphones XB500 and compare with alternatives."
    print(f"\n  You: {prompt_c}")
    reply_c = await _ask(research_runner, uid_c, sid_c, prompt_c, record=False)
    print(f"\n  [eComBot research]\n{_wrap(reply_c)}\n")

    _sep("=")

# REPL
async def repl(runner, user_id: str, session_id: str) -> None:
    print("\n  Type your message (or  q  to quit):\n")
    while True:
        try:
            prompt = input("  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if prompt.lower() == "q":
            break
        if not prompt:
            continue

        reply = await _ask(runner, user_id, session_id, prompt)
        print(f"\n  [eComBot]\n{_wrap(reply)}\n")

    print("  Goodbye.\n")

# Main
async def main() -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        print(
            "\n[ERROR] OPENROUTER_API_KEY is not set.\n"
            "Add it to a .env file:  OPENROUTER_API_KEY=your-key-here\n"
        )
        return

        enable_routing_callbacks()

    skip_scenarios = "--repl" in sys.argv

    backend_label = _BACKEND.upper()
    print(f"""
+========================================================================+
|          eComBot Capstone — Support Agent Demo                        |
|   Model   : google/gemini-2.5-flash  (OpenRouter + LiteLLM)          |
|   Backend : {backend_label:<55}  |
+========================================================================+""")

        if _DB_MODE:
        print()
        pg_status = "OK" if pg_ok() else "UNREACHABLE"
        redis_status = "OK" if redis_ok() else "UNREACHABLE"
        print(f"  PostgreSQL : {pg_status}")
        print(f"  Redis      : {redis_status}")
        if pg_status != "OK":
            print("\n  [ERROR] PostgreSQL is not reachable. Run:  docker compose up -d")
            return

    print(_GUIDE)

    runner, user_id, session_id = await make_runner(orchestrator)
    print(f"  Session: {session_id}  User: {user_id}\n")

        if _DB_MODE:
        save_session_ref(user_id, session_id)

    if not skip_scenarios:
        await run_scenarios(runner, user_id, session_id)
        await run_day09a_demos()

    await repl(runner, user_id, session_id)

if __name__ == "__main__":
    asyncio.run(main())
