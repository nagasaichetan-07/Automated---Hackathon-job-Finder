"""
Aegis — Opportunity ORM Model

Canonical storage model for normalized opportunities (jobs, internships, hackathons).
All connectors normalize source data into this structure.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from core.schemas.domain import OpportunityCategory
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from storage.models.base import Base


class Opportunity(Base):
    """Canonical opportunity record."""

    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_opportunity_source_external"),
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
    external_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Unique identifier from the source",
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(
        String(50),
        default=OpportunityCategory.JOB.value,
        nullable=False,
        comment="job, internship, or hackathon",
    )
    organizer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mode: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="remote, onsite, or hybrid",
    )
    eligibility_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Raw eligibility requirements snippet from source",
    )
    team_size_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    team_size_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prize: Mapped[str | None] = mapped_column(String(255), nullable=True)
    skills_themes: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Field-level source evidence quotes",
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash for dedup/change detection",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
