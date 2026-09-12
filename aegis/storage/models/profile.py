"""
Aegis — Profile ORM Model

SQLAlchemy ORM entity for student profiles, linking authoritative facts,
draft résumé extractions, and verification flags.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from storage.models.base import Base


class Profile(Base):
    """Student profile entity."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        unique=True,
        nullable=False,
        index=True,
    )

    # Authoritative facts (only populated directly by user or confirmed from résumé)
    education_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    branch: Mapped[str | None] = mapped_column(String(150), nullable=True)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    preferred_locations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    opportunity_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    interests: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Résumé raw & draft extraction fields
    resume_raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_extracted: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Draft extracted fields awaiting user confirmation",
    )
    resume_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Must be True for extracted fields to be authoritative",
    )
    resume_evidence: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Source text snippets and confidence scores per field",
    )
