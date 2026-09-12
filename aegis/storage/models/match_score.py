"""
Aegis — MatchScore ORM Model

Stores the transparent hybrid match score breakdown, plain-language fact-grounded explanation,
and user feedback for an opportunity-profile pair (AC-3.5, AC-3.6, AC-3.7).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from storage.models.base import Base


class MatchScore(Base):
    """Hybrid match score record with full breakdown and explanation."""

    __tablename__ = "match_scores"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "profile_id", name="uq_match_opportunity_profile"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    final_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Composite score [0.0, 1.0] (clamped to 0.0 on INELIGIBLE)",
    )
    eligibility_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Eligibility sub-score (1.0 for ELIGIBLE, 0.5 for UNKNOWN, 0.0 for INELIGIBLE)",
    )
    feature_overlap_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Structured feature overlap (skills, location, category) [0.0, 1.0]",
    )
    semantic_similarity_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Semantic embedding similarity [0.0, 1.0]",
    )
    weights_used: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Weights used for transparency",
    )
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Granular feature and rule scores for audit",
    )
    explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Fact-grounded plain language explanation",
    )
    user_feedback: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="interested, dismissed, applied, not_eligible",
    )
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
