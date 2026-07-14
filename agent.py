"""
agent.py — ADK Web entry point
--------------------------------
Exposes `root_agent` for ADK Web discovery.

Run from the project root:
    adk web

Then open http://localhost:8000 and select the ecombot agent.
"""

import os
import sys

# Ensure src/ is importable
_SRC = os.path.join(os.path.dirname(__file__), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from dotenv import load_dotenv
load_dotenv()

from agents.orchestrator import orchestrator

# ADK Web looks for `root_agent`
root_agent = orchestrator
