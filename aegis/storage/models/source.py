"""
Aegis — Source ORM Model

SQLAlchemy ORM model for data sources (APIs, Web extractors, RSS feeds),
tracking collection cadence, configuration, and health state transitions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from core.schemas.domain import SourceHealth
from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from storage.models.base import Base


class Source(Base):
    """Data source configuration entity."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="api, web, or rss",
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    connector_class: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Python class path or registered key for the connector",
    )
    connector_config: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Source-specific parameters like board_token, site, headers",
    )
    cadence: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="0 */6 * * *",
        comment="Cron expression or interval format for Celery Beat scheduling",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )
    health_state: Mapped[str] = mapped_column(
        String(50),
        default=SourceHealth.HEALTHY.value,
        nullable=False,
        comment="HEALTHY, DEGRADED, or BROKEN",
    )
    access_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Terms of service, robot access verification, or API notes",
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
