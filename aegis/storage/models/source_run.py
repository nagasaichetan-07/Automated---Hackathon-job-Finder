"""
Aegis — Source Run Metric ORM Model

Tracks execution metrics for every autonomous collection job: status, record count,
execution latency, and error diagnostics for observability and self-healing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from storage.models.base import Base


class SourceRun(Base):
    """Metric record for an autonomous source collection execution."""

    __tablename__ = "source_runs"

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
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="success or failure",
    )
    record_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    duration_seconds: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
