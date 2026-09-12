"""
Aegis — Repair Run & Patch ORM Models

SQLAlchemy ORM models for self-healing repair runs and patch lifecycle tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from core.schemas.domain import FailureClass, RepairRunOutcome, RepairState, RepairTriggerType
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from storage.models.base import Base


class RepairRun(Base):
    """Audit record for an autonomous or manual self-healing repair attempt."""

    __tablename__ = "repair_runs"

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
    trigger_type: Mapped[str] = mapped_column(
        String(50),
        default=RepairTriggerType.AUTOMATIC.value,
        nullable=False,
    )
    failure_class: Mapped[str] = mapped_column(
        String(50),
        default=FailureClass.SELECTOR_NOT_FOUND.value,
        nullable=False,
    )
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnosis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    outcome: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="SUCCESS, FAILURE, REJECTED, or ROLLED_BACK",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    patches: Mapped[list[RepairPatch]] = relationship(
        "RepairPatch",
        back_populates="repair_run",
        cascade="all, delete-orphan",
    )


class RepairPatch(Base):
    """A proposed code patch associated with a repair run."""

    __tablename__ = "repair_patches"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    repair_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("repair_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state: Mapped[str] = mapped_column(
        String(50),
        default=RepairState.PROPOSED.value,
        nullable=False,
        index=True,
    )
    diff_content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Unified diff — minimal patch targeting connector",
    )
    target_file: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Relative path to connector file being repaired",
    )
    test_results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    sandbox_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    connector_version_before: Mapped[str | None] = mapped_column(Text, nullable=True)
    connector_version_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rolled_back_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    repair_run: Mapped[RepairRun] = relationship(
        "RepairRun",
        back_populates="patches",
    )
