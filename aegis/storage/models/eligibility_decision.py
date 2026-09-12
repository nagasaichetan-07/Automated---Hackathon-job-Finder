"""
Aegis — EligibilityDecision ORM Model

Records the deterministic eligibility evaluation of an opportunity for a student profile.
State is strictly ELIGIBLE, INELIGIBLE, or UNKNOWN with rule audit evidence (§2.4).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from core.schemas.domain import EligibilityState
from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from storage.models.base import Base


class EligibilityDecision(Base):
    """Eligibility evaluation record for an opportunity-profile pair."""

    __tablename__ = "eligibility_decisions"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "profile_id", name="uq_eligibility_opportunity_profile"),
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
    state: Mapped[str] = mapped_column(
        String(50),
        default=EligibilityState.UNKNOWN.value,
        nullable=False,
        comment="ELIGIBLE, INELIGIBLE, or UNKNOWN",
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Rule-level evidence citations and rationale",
    )
    rule_results: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Per-rule pass/fail/unknown details",
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Evaluation confidence (0.0 to 1.0)",
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
