"""
Aegis — Notification ORM Model

Tracks all notification events across email, telegram, and in-app channels.
Guarantees absolute deduplication via unique idempotency_key (AC-4.2).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from storage.models.base import Base


class Notification(Base):
    """Notification event record with idempotency guarantee and delivery audit."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_notification_idempotency_key"),
        Index("ix_notifications_profile_status", "profile_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="email | telegram | in_app",
    )
    notification_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="immediate | digest",
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA256(user_id + opportunity_id + version_hash)",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
        comment="pending | sent | failed",
    )
    content: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Rendered notification content (title, category, score, etc.)",
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Scheduled delivery timestamp (used for quiet hours deferral)",
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when actually sent",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
