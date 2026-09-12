"""
Aegis — Notification Repository

Provides database access, idempotency checking, and status lifecycle management
for Notification entities.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from storage.models.notification import Notification


class NotificationRepository:
    """Repository managing Notification persistence, deduplication, and queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        """Fetch notification by primary key ID."""
        stmt = select(Notification).where(Notification.id == notification_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Notification | None:
        """Fetch notification by unique idempotency key."""
        stmt = select(Notification).where(Notification.idempotency_key == idempotency_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_notification(
        self,
        profile_id: uuid.UUID,
        opportunity_id: uuid.UUID,
        channel: str,
        notification_type: str,
        idempotency_key: str,
        content: dict[str, Any],
        status: str = "pending",
        scheduled_at: datetime | None = None,
        sent_at: datetime | None = None,
    ) -> Notification | None:
        """
        Create a new notification record.
        Returns the created Notification, or None if the idempotency_key already exists.
        """
        # First check explicitly to avoid unnecessary transaction rollback
        existing = await self.get_by_idempotency_key(idempotency_key)
        if existing:
            return None

        notification = Notification(
            profile_id=profile_id,
            opportunity_id=opportunity_id,
            channel=channel,
            notification_type=notification_type,
            idempotency_key=idempotency_key,
            content=content,
            status=status,
            scheduled_at=scheduled_at,
            sent_at=sent_at,
            created_at=datetime.now(UTC),
        )
        self.session.add(notification)
        try:
            await self.session.flush()
            return notification
        except IntegrityError:
            # Race condition: another worker inserted same key concurrently
            await self.session.rollback()
            return None

    async def list_for_profile(
        self,
        profile_id: uuid.UUID,
        status: str | None = None,
        channel: str | None = None,
        notification_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """List notifications for a user profile, ordered by created_at descending."""
        stmt = select(Notification).where(Notification.profile_id == profile_id)
        if status:
            stmt = stmt.where(Notification.status == status)
        if channel:
            stmt = stmt.where(Notification.channel == channel)
        if notification_type:
            stmt = stmt.where(Notification.notification_type == notification_type)

        stmt = stmt.order_by(desc(Notification.created_at)).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_due(
        self,
        as_of: datetime | None = None,
        limit: int = 100,
    ) -> list[Notification]:
        """
        Fetch pending notifications ready for delivery.
        Matches notifications where status='pending' and (scheduled_at IS NULL or scheduled_at <= as_of).
        """
        threshold = as_of or datetime.now(UTC)
        stmt = (
            select(Notification)
            .where(
                Notification.status == "pending",
                or_(
                    Notification.scheduled_at.is_(None),
                    Notification.scheduled_at <= threshold,
                ),
            )
            .order_by(Notification.scheduled_at.asc().nullsfirst())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_as_sent(
        self,
        notification_id: uuid.UUID,
        sent_at: datetime | None = None,
    ) -> bool:
        """Mark a notification as successfully sent."""
        notification = await self.get_by_id(notification_id)
        if not notification:
            return False
        notification.status = "sent"
        notification.sent_at = sent_at or datetime.now(UTC)
        return True

    async def mark_as_failed(
        self,
        notification_id: uuid.UUID,
        error_message: str,
    ) -> bool:
        """Mark a notification as failed and record the error."""
        notification = await self.get_by_id(notification_id)
        if not notification:
            return False
        notification.status = "failed"
        updated_content = dict(notification.content) if notification.content else {}
        updated_content["error"] = error_message
        notification.content = updated_content
        return True
