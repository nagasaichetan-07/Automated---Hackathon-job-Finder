"""
Aegis — Source Repository

Async repository for creating, retrieving, updating, and managing data sources,
including automated health state transitions (HEALTHY -> DEGRADED -> BROKEN).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.schemas.domain import SourceHealth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from storage.models.source import Source


class SourceRepository:
    """Async database repository for data sources."""

    @staticmethod
    async def get_by_id(session: AsyncSession, source_id: uuid.UUID) -> Source | None:
        """Fetch a source by primary key."""
        result = await session.execute(select(Source).where(Source.id == source_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_name(session: AsyncSession, name: str) -> Source | None:
        """Fetch a source by its unique human-readable name."""
        result = await session.execute(select(Source).where(Source.name == name))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_sources(
        session: AsyncSession,
        enabled_only: bool = False,
        health_state: str | None = None,
    ) -> list[Source]:
        """List all registered sources with optional filtering."""
        query = select(Source)
        if enabled_only:
            query = query.where(Source.enabled.is_(True))
        if health_state:
            query = query.where(Source.health_state == health_state)
        query = query.order_by(Source.name.asc())
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create_source(
        session: AsyncSession,
        *,
        name: str,
        source_type: str,
        url: str,
        connector_class: str,
        connector_config: dict[str, Any] | None = None,
        cadence: str = "0 */6 * * *",
        enabled: bool = True,
        access_notes: str | None = None,
    ) -> Source:
        """Create and persist a new data source."""
        source = Source(
            id=uuid.uuid4(),
            name=name,
            source_type=source_type,
            url=url,
            connector_class=connector_class,
            connector_config=connector_config or {},
            cadence=cadence,
            enabled=enabled,
            health_state=SourceHealth.HEALTHY.value,
            access_notes=access_notes,
            consecutive_failures=0,
        )
        session.add(source)
        await session.flush()
        return source

    @staticmethod
    async def update_source(
        session: AsyncSession,
        source_id: uuid.UUID,
        **updates: Any,
    ) -> Source | None:
        """Update fields on an existing source."""
        source = await SourceRepository.get_by_id(session, source_id)
        if not source:
            return None

        allowed_fields = {
            "name",
            "url",
            "source_type",
            "connector_class",
            "connector_config",
            "cadence",
            "enabled",
            "access_notes",
            "health_state",
        }
        for key, val in updates.items():
            if key in allowed_fields and val is not None:
                setattr(source, key, val)

        await session.flush()
        return source

    @staticmethod
    async def delete_source(session: AsyncSession, source_id: uuid.UUID) -> bool:
        """Delete a source by ID."""
        source = await SourceRepository.get_by_id(session, source_id)
        if not source:
            return False
        await session.delete(source)
        await session.flush()
        return True

    @staticmethod
    async def record_run_outcome(
        session: AsyncSession,
        source_id: uuid.UUID,
        *,
        success: bool,
        run_time: datetime | None = None,
    ) -> Source | None:
        """
        Record collection outcome and apply health state transition machine:
        - Success: consecutive_failures=0, health_state=HEALTHY, update last_success_at
        - 1 or 2 consecutive failures: health_state=DEGRADED
        - >= 3 consecutive failures: health_state=BROKEN
        """
        source = await SourceRepository.get_by_id(session, source_id)
        if not source:
            return None

        now = run_time or datetime.now(UTC)
        source.last_run_at = now

        if success:
            source.consecutive_failures = 0
            source.health_state = SourceHealth.HEALTHY.value
            source.last_success_at = now
        else:
            source.consecutive_failures += 1
            if source.consecutive_failures >= 3:
                source.health_state = SourceHealth.BROKEN.value
            else:
                source.health_state = SourceHealth.DEGRADED.value

        await session.flush()
        return source
