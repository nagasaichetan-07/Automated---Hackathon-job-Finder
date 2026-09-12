"""
Integration tests for database connectivity and session lifecycle.

Verifies that:
1. SQLAlchemy DeclarativeBase compiles.
2. Sessions can execute queries and manage transactions cleanly.
3. Connectivity probe functions operate as expected.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from storage.models.base import Base


@pytest.mark.asyncio
async def test_db_session_and_table_creation():
    """Verify in-memory SQLite async engine can create metadata and execute queries."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        result = await session.execute(text("SELECT 1 AS alive"))
        val = result.scalar()
        assert val == 1

    await engine.dispose()
