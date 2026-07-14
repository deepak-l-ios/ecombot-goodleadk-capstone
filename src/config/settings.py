"""
settings.py — Centralized configuration for eComBot capstone
-------------------------------------------------------------
All service credentials are read from environment variables (or .env).
No secrets are hardcoded here.

Usage:
    from config.settings import settings
    pool = psycopg2.connect(dsn=settings.pg_dsn)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

@dataclass
class Settings:
    # ── PostgreSQL ─────────────────────────────────────────────────────────
    pg_host: str = field(default_factory=lambda: os.getenv("PG_HOST", "localhost"))
    pg_port: int = field(default_factory=lambda: int(os.getenv("PG_PORT", "5432")))
    pg_db: str = field(default_factory=lambda: os.getenv("PG_DB", "ecombot"))
    pg_user: str = field(default_factory=lambda: os.getenv("PG_USER", "ecombot"))
    pg_password: str = field(default_factory=lambda: os.getenv("PG_PASSWORD", ""))

    # ── Redis ──────────────────────────────────────────────────────────────
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    redis_password: str = field(default_factory=lambda: os.getenv("REDIS_PASSWORD", ""))
    redis_session_ttl: int = field(
        default_factory=lambda: int(os.getenv("REDIS_SESSION_TTL", "3600"))
    )

    # ChromaDB / RAG
    chroma_collection: str = field(
        default_factory=lambda: os.getenv("CHROMA_COLLECTION", "ecombot_kb")
    )
    # Persist directory relative to project root; can be overridden via env var.
    _chroma_persist_dir_raw: str = field(
        default_factory=lambda: os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db"),
        repr=False,
    )

    # Embedding model — uses OpenRouter's OpenAI-compatible /embeddings endpoint.
    # The same OPENROUTER_API_KEY used for chat is also used for embeddings.
    embedding_model: str = field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_MODEL", "openrouter/openai/text-embedding-3-small"
        )
    )

    # LiteLLM routing
    fast_model: str = field(
        default_factory=lambda: os.getenv("FAST_MODEL", "openrouter/google/gemini-2.5-flash")
    )
    deep_model: str = field(
        default_factory=lambda: os.getenv("DEEP_MODEL", "openrouter/google/gemini-2.5-pro")
    )
    backup_model: str = field(
        default_factory=lambda: os.getenv("BACKUP_MODEL", "openrouter/openai/gpt-4o-mini")
    )

    # LangSmith
    langsmith_api_key: str = field(
        default_factory=lambda: os.getenv("LANGSMITH_API_KEY", "")
    )
    langsmith_project: str = field(
        default_factory=lambda: os.getenv("LANGSMITH_PROJECT", "ecombot-capstone")
    )

    # ── Derived connection strings ─────────────────────────────────────────

    @property
    def redis_url(self) -> str:
        """Redis URL for ADK RedisSessionService."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}"
        return f"redis://{self.redis_host}:{self.redis_port}"

    @property
    def chroma_persist_dir(self) -> Path:
        """Absolute path to the ChromaDB persist directory."""
        p = Path(self._chroma_persist_dir_raw)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        return p

    @property
    def pg_dsn(self) -> str:
        """psycopg2-compatible connection string."""
        return (
            f"host={self.pg_host} port={self.pg_port} "
            f"dbname={self.pg_db} user={self.pg_user} "
            f"password={self.pg_password}"
        )

    @property
    def adk_db_url(self) -> str:
        """SQLAlchemy URL for ADK DatabaseSessionService.
        Must use asyncpg — ADK's DatabaseSessionService requires an async driver.
        psycopg2 (sync) is used only by db.py's ThreadedConnectionPool.
        """
        return (
            f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

# Module-level singleton — import this everywhere.
settings = Settings()
