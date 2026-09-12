"""
Aegis — Notification Dispatcher (MVP-4)

Coordinates notification deduplication (AC-4.2), version change detection (AC-4.3),
quiet hours scheduling (AC-4.4), content rendering (AC-4.5), and multi-channel delivery.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.logging.logger import setup_logging
from core.schemas.domain import EligibilityState
from notifications.email.backend import EmailBackend, get_email_backend
from notifications.idempotency import (
    compute_digest_idempotency_key,
    compute_idempotency_key,
    compute_opportunity_version_hash,
)
from notifications.quiet_hours import is_in_quiet_hours, next_active_time
from notifications.renderer import render_daily_digest, render_immediate_notification
from sqlalchemy.ext.asyncio import AsyncSession
from storage.models.notification import Notification
from storage.repositories.notification_repository import NotificationRepository

logger = setup_logging()


class NotificationDispatcher:
    """Core autonomous notification coordinator."""

    def __init__(
        self,
        session: AsyncSession,
        email_backend: EmailBackend | None = None,
    ) -> None:
        self.session = session
        self.repo = NotificationRepository(session)
        self.email_backend = email_backend or get_email_backend()

    async def dispatch_immediate_match(
        self,
        profile: Any,
        opportunity: Any,
        match_score: Any,
        eligibility: Any,
        min_score_threshold: float = 0.65,
        as_of: datetime | None = None,
        user_email: str | None = None,
    ) -> Notification | None:
        """
        Evaluates and dispatches an immediate notification for a high-value match.
        Respects:
        - Disqualification: INELIGIBLE matches never notify
        - Score threshold: matches below min_score_threshold are ignored
        - Idempotency: SHA256(user_id + opportunity_id + version_hash) prevents duplicates
        - Quiet hours: during quiet hours, status='pending' and scheduled_at is set to active window
        """
        now = as_of or datetime.now(UTC)

        # 0. Hackathon Visibility Filter check
        from opportunity.filters import is_hackathon_visible
        if not is_hackathon_visible(opportunity, now=now):
            logger.info("Skipping notification: opportunity failed hackathon visibility filter")
            return None

        # 1. Eligibility check: Hard disqualifications never trigger notifications
        state = getattr(eligibility, "state", None)
        if isinstance(state, EligibilityState) and state == EligibilityState.INELIGIBLE:
            return None
        if str(state).upper() == "INELIGIBLE":
            return None

        # 2. Score threshold check
        final_score = getattr(match_score, "final_score", 0.0)
        if final_score < min_score_threshold:
            return None

        # 3. Meaningful version hash and Idempotency key
        version_hash = compute_opportunity_version_hash(opportunity)
        user_id_raw = getattr(profile, "user_id", getattr(profile, "id", None))
        user_id: uuid.UUID | str = user_id_raw if user_id_raw is not None else uuid.uuid4()
        opp_id_raw = getattr(opportunity, "id", None)
        opp_id: uuid.UUID = (
            opp_id_raw
            if isinstance(opp_id_raw, uuid.UUID)
            else (uuid.UUID(str(opp_id_raw)) if opp_id_raw else uuid.uuid4())
        )
        idempotency_key = compute_idempotency_key(user_id, opp_id, version_hash)

        # 4. Check if already notified for this exact version
        existing = await self.repo.get_by_idempotency_key(idempotency_key)
        if existing:
            logger.info("Skipping notification: idempotency key %s already exists", idempotency_key[:12])
            return None

        # 5. Render notification content (satisfies AC-4.5)
        content = render_immediate_notification(opportunity, match_score, eligibility)
        recipient: str = str(user_email or getattr(profile, "email", "student@example.com"))
        content["recipient"] = recipient

        # 6. Quiet Hours Evaluation (AC-4.4)
        quiet_start = getattr(profile, "quiet_hours_start", 22)
        quiet_end = getattr(profile, "quiet_hours_end", 8)
        in_quiet = is_in_quiet_hours(now, quiet_start=quiet_start, quiet_end=quiet_end)

        profile_id_raw = getattr(profile, "id", user_id)
        profile_id: uuid.UUID = (
            profile_id_raw
            if isinstance(profile_id_raw, uuid.UUID)
            else (uuid.UUID(str(profile_id_raw)) if profile_id_raw else uuid.uuid4())
        )

        if in_quiet:
            scheduled_time = next_active_time(now, quiet_start=quiet_start, quiet_end=quiet_end)
            logger.info(
                "Quiet hours active: queuing notification for %s at %s",
                recipient,
                scheduled_time.isoformat(),
            )
            notification = await self.repo.create_notification(
                profile_id=profile_id,
                opportunity_id=opp_id,
                channel="email",
                notification_type="immediate",
                idempotency_key=idempotency_key,
                content=content,
                status="pending",
                scheduled_at=scheduled_time,
            )
        else:
            # Deliver immediately
            sent_success = self.email_backend.send_email(
                to_email=recipient,
                subject=content["subject"],
                html_body=content["html_body"],
                text_body=content["text_body"],
            )
            status = "sent" if sent_success else "failed"
            notification = await self.repo.create_notification(
                profile_id=profile_id,
                opportunity_id=opp_id,
                channel="email",
                notification_type="immediate",
                idempotency_key=idempotency_key,
                content=content,
                status=status,
                sent_at=now if sent_success else None,
            )

        return notification

    async def dispatch_daily_digest(
        self,
        profile: Any,
        top_items: list[dict[str, Any]],
        digest_date: str | None = None,
        user_email: str | None = None,
    ) -> Notification | None:
        """
        Consolidates top opportunity matches into a single daily digest (AC-4.1).
        Uses daily digest idempotency key to prevent double digests on the same day.
        """
        if not top_items:
            return None

        from opportunity.filters import is_hackathon_visible
        top_items = [item for item in top_items if is_hackathon_visible(item)]
        if not top_items:
            logger.info("Skipping daily digest: no items passed hackathon visibility filter")
            return None

        date_str = digest_date or datetime.now(UTC).strftime("%Y-%m-%d")
        user_id = getattr(profile, "user_id", getattr(profile, "id", "unknown"))
        idempotency_key = compute_digest_idempotency_key(user_id, date_str)

        # Check if digest was already dispatched today
        existing = await self.repo.get_by_idempotency_key(idempotency_key)
        if existing:
            logger.info("Daily digest already sent for user %s on %s", user_id, date_str)
            return None

        recipient: str = str(user_email or getattr(profile, "email", "student@example.com"))
        user_name = getattr(profile, "full_name", None)

        content = render_daily_digest(top_items, user_name=user_name)
        content["recipient"] = recipient
        content["digest_date"] = date_str

        sent_success = self.email_backend.send_email(
            to_email=recipient,
            subject=content["subject"],
            html_body=content["html_body"],
            text_body=content["text_body"],
        )

        profile_id_raw = getattr(profile, "id", user_id)
        profile_id: uuid.UUID = (
            profile_id_raw
            if isinstance(profile_id_raw, uuid.UUID)
            else (uuid.UUID(str(profile_id_raw)) if profile_id_raw else uuid.uuid4())
        )

        # Use first item's opportunity_id as reference
        primary_opp_id_raw = top_items[0].get("opportunity_id", profile_id)
        primary_opp_id: uuid.UUID = (
            primary_opp_id_raw
            if isinstance(primary_opp_id_raw, uuid.UUID)
            else (uuid.UUID(str(primary_opp_id_raw)) if primary_opp_id_raw else profile_id)
        )

        notification = await self.repo.create_notification(
            profile_id=profile_id,
            opportunity_id=primary_opp_id,
            channel="email",
            notification_type="digest",
            idempotency_key=idempotency_key,
            content=content,
            status="sent" if sent_success else "failed",
            sent_at=datetime.now(UTC) if sent_success else None,
        )
        return notification

    async def process_pending_scheduled(
        self,
        as_of: datetime | None = None,
    ) -> int:
        """
        Sweeps pending notifications that were scheduled (e.g. held back by quiet hours)
        whose scheduled_at is now due, delivering them via email.
        """
        now = as_of or datetime.now(UTC)
        pending = await self.repo.get_pending_due(as_of=now)
        delivered_count = 0

        for notif in pending:
            content = notif.content or {}
            recipient = content.get("recipient", "student@example.com")
            subject = content.get("subject", "Aegis Opportunity Notification")
            html_body = content.get("html_body", "")
            text_body = content.get("text_body", "")

            sent = self.email_backend.send_email(
                to_email=recipient,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )
            if sent:
                await self.repo.mark_as_sent(notif.id, sent_at=now)
                delivered_count += 1
            else:
                await self.repo.mark_as_failed(notif.id, error_message="Delivery failed during scheduled sweep")

        return delivered_count
