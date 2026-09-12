"""
Aegis — Database Engine and Health Probes

Manages database connections, engine lifecycles, and health checks for PostgreSQL and Redis.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from core.config.settings import get_settings
from core.logging.logger import setup_logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = setup_logging()
settings = get_settings()

# Create async engine with connection pooling
# If in development or testing without postgres running, allow pool pre-ping
async_engine = create_async_engine(
    settings.database_url,
    echo=(settings.environment == "development" and settings.log_level == "DEBUG"),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connectivity(timeout_seconds: float = 2.0) -> tuple[bool, str]:
    """
    Probe database readiness by running 'SELECT 1;'.
    Returns (True, 'ok') on success, (False, error_message) on failure.
    """
    try:
        async with asyncio.timeout(timeout_seconds):
            async with async_engine.connect() as conn:
                result = await conn.execute(text("SELECT 1;"))
                row = result.scalar()
                if row == 1:
                    return True, "ok"
                return False, f"Unexpected response: {row}"
    except Exception as exc:
        return False, str(exc)


async def check_redis_connectivity(timeout_seconds: float = 2.0) -> tuple[bool, str]:
    """
    Probe Redis readiness by pinging.
    Returns (True, 'ok') on success, (False, error_message) on failure.
    """
    client = None
    try:
        async with asyncio.timeout(timeout_seconds):
            client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=timeout_seconds,
            )
            pong = await client.ping()
            if pong:
                return True, "ok"
            return False, "Failed to receive PONG from Redis"
    except Exception as exc:
        return False, str(exc)
    finally:
        if client is not None:
            await client.aclose()
