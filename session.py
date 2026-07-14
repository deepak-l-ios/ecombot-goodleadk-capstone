"""
session.py — Session service factory
--------------------------------------
Selects the session backend based on SESSION_BACKEND env var:

    SESSION_BACKEND=memory    — InMemorySessionService  (default)
    SESSION_BACKEND=redis     — RedisSessionService
    SESSION_BACKEND=database  — DatabaseSessionService  (PostgreSQL)

Examples:
    SESSION_BACKEND=memory   python demo.py
    SESSION_BACKEND=database python demo.py
    SESSION_BACKEND=redis    python demo.py
"""

import logging
import os
import sys
import uuid

# Ensure src/ is on the path so relative service imports work
_SRC = os.path.join(os.path.dirname(__file__), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

log = logging.getLogger(__name__)

APP_NAME = "ecombot-capstone"

def get_session_service():
    """
    Return the active session service based on SESSION_BACKEND env var.
    """
    backend = os.getenv("SESSION_BACKEND", "memory").lower()

    if backend == "memory":
        log.info("Session backend: InMemory (no persistence)")
        return InMemorySessionService()

    if backend == "redis":
        try:
            from adk_extra_services.sessions import RedisSessionService
            from config.settings import settings
            svc = RedisSessionService(redis_url=settings.redis_url)
            log.info("Session backend: Redis (%s:%s)", settings.redis_host, settings.redis_port)
            return svc
        except Exception as exc:
            log.error("Redis session service unavailable: %s", exc)
            raise RuntimeError(
                "Cannot connect to Redis for session storage. "
                "Start it with:  docker compose up -d redis\n"
                f"Detail: {exc}"
            ) from exc

    # Default: database (PostgreSQL via asyncpg)
    try:
        from google.adk.sessions import DatabaseSessionService
        from config.settings import settings
        svc = DatabaseSessionService(db_url=settings.adk_db_url)
        log.info(
            "Session backend: PostgreSQL (%s:%s/%s)",
            settings.pg_host, settings.pg_port, settings.pg_db,
        )
        return svc
    except Exception as exc:
        log.error("PostgreSQL session service unavailable: %s", exc)
        raise RuntimeError(
            "Cannot connect to PostgreSQL for session storage. "
            "Start the database with:  docker compose up -d postgres\n"
            f"Detail: {exc}"
        ) from exc

async def make_runner(
    agent,
    user_id: str | None = None,
    session_id: str | None = None,
) -> tuple[Runner, str, str]:
    """
    Wrap an agent in a Runner with a session.

    - If session_id is None, a fresh session is created.
    - If session_id is provided, the existing session is reused (state
      is loaded from the backend automatically).

    Returns (runner, user_id, session_id).
    """
    session_service = get_session_service()
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    if user_id is None:
        user_id = f"user-{uuid.uuid4().hex[:6]}"

    if session_id is None:
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        log.info("Created new session: %s / %s", user_id, session_id)
    else:
        # Reconnect: verify the session exists, create if missing
        try:
            existing = await session_service.get_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )
        except Exception:
            existing = None

        if existing is None:
            await session_service.create_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )
            log.info("Session not found — created fresh: %s", session_id)
        else:
            log.info("Reconnected to existing session: %s", session_id)

    return runner, user_id, session_id
