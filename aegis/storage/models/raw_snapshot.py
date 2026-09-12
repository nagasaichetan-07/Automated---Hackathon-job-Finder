"""
Aegis — Raw Snapshot ORM Model

Immutable record of raw data collected from a source, indexed by content hash
for auditability, reproducibility, and idempotent deduplication.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from storage.models.base import Base


class RawSnapshot(Base):
    """Immutable raw snapshot of ingested source data."""

    __tablename__ = "raw_snapshots"
    __table_args__ = (
        UniqueConstraint("source_id", "content_hash", name="uq_raw_snapshot_source_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="SHA-256 hash of the raw response payload",
    )
    raw_payload: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Raw JSON string, XML text, or body content",
    )
    record_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
