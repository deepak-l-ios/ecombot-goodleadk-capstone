"""
session_service.py — Redis working-memory cache for eComBot
-------------------------------------------------------------
Redis is used as a fast working-memory cache:
  - Session state (current_order_id, current_customer_name, current_product_id) is
    snapshotted here with a TTL so it survives short process restarts
    without a full DB read.
  - The canonical session state lives in PostgreSQL (ADK DatabaseSessionService).
  - All Redis errors are caught and logged; the app continues without caching.

Public API:
    save_session_state(session_id, state)   → None
    load_session_state(session_id)          → dict | None
    save_session_ref(user_id, session_id)   → None
    load_session_ref(user_id)               → str | None
    check_connection()                      → bool
"""

import json
import logging

import redis

from config.settings import settings

log = logging.getLogger(__name__)

_client: redis.Redis | None = None

def _get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            decode_responses=True,
            socket_connect_timeout=3,
        )
    return _client

def save_session_state(session_id: str, state: dict) -> None:
    """Snapshot session working memory to Redis with TTL."""
    try:
        key = f"ecombot:state:{session_id}"
        _get_redis().setex(key, settings.redis_session_ttl, json.dumps(state))
    except redis.RedisError as exc:
        log.warning("Redis unavailable — state not cached: %s", exc)

def load_session_state(session_id: str) -> dict | None:
    """
    Load session working memory from Redis.
    Returns None if the key is missing or Redis is down.
    """
    try:
        raw = _get_redis().get(f"ecombot:state:{session_id}")
        return json.loads(raw) if raw else None
    except redis.RedisError as exc:
        log.warning("Redis unavailable — cannot load cached state: %s", exc)
        return None

def save_session_ref(user_id: str, session_id: str) -> None:
    """
    Store the most recent session_id for a user so it can be recovered
    after a process restart without the caller needing to remember the ID.
    """
    try:
        key = f"ecombot:session_ref:{user_id}"
        _get_redis().setex(key, settings.redis_session_ttl, session_id)
    except redis.RedisError as exc:
        log.warning("Redis unavailable — session ref not saved: %s", exc)

def load_session_ref(user_id: str) -> str | None:
    """Return the last active session_id for a user, or None."""
    try:
        return _get_redis().get(f"ecombot:session_ref:{user_id}")
    except redis.RedisError as exc:
        log.warning("Redis unavailable — cannot load session ref: %s", exc)
        return None

def check_connection() -> bool:
    """Return True if Redis is reachable."""
    try:
        return _get_redis().ping()
    except redis.RedisError:
        return False
