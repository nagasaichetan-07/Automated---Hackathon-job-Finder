"""
Aegis — Raw Snapshot & Run Metrics Repository

Provides async database access for immutable raw payload snapshots (with SHA-256
hash-based deduplication) and run metric auditing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from storage.models.raw_snapshot import RawSnapshot
from storage.models.source_run import SourceRun


class SnapshotRepository:
    """Async repository for raw snapshots and run metrics."""

    @staticmethod
    async def get_snapshot_by_hash(
        session: AsyncSession,
        source_id: uuid.UUID,
        content_hash: str,
    ) -> RawSnapshot | None:
        """Find a snapshot for a source with an identical content hash (idempotency check)."""
        result = await session.execute(
            select(RawSnapshot).where(
                RawSnapshot.source_id == source_id,
                RawSnapshot.content_hash == content_hash,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def save_raw_snapshot(
        session: AsyncSession,
        *,
        source_id: uuid.UUID,
        content_hash: str,
        raw_payload: str,
        record_count: int,
        collected_at: datetime | None = None,
    ) -> RawSnapshot:
        """Persist a new raw response snapshot."""
        snapshot = RawSnapshot(
            id=uuid.uuid4(),
            source_id=source_id,
            content_hash=content_hash,
            raw_payload=raw_payload,
            record_count=record_count,
            collected_at=collected_at or datetime.now(UTC),
        )
        session.add(snapshot)
        await session.flush()
        return snapshot

    @staticmethod
    async def record_source_run(
        session: AsyncSession,
        *,
        source_id: uuid.UUID,
        status: str,
        record_count: int,
        duration_seconds: float,
        error_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> SourceRun:
        """Record an execution metric for a source collection attempt."""
        now = datetime.now(UTC)
        run = SourceRun(
            id=uuid.uuid4(),
            source_id=source_id,
            status=status,
            record_count=record_count,
            duration_seconds=duration_seconds,
            error_message=error_message,
            started_at=started_at or now,
            completed_at=completed_at or now,
        )
        session.add(run)
        await session.flush()
        return run

    @staticmethod
    async def list_runs_for_source(
        session: AsyncSession,
        source_id: uuid.UUID,
        limit: int = 20,
    ) -> list[SourceRun]:
        """Fetch recent execution runs for a source."""
        result = await session.execute(
            select(SourceRun)
            .where(SourceRun.source_id == source_id)
            .order_by(desc(SourceRun.started_at))
            .limit(limit)
        )
        return list(result.scalars().all())
