"""
Aegis — Notifications API Router (Phase 6)

Provides endpoints to query notification history, trigger test alerts,
and configure quiet hours preferences.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from storage.database import get_db_session
from storage.repositories.match_repository import MatchRepository
from storage.repositories.notification_repository import NotificationRepository
from storage.repositories.opportunity_repository import OpportunityRepository
from storage.repositories.profile_repository import ProfileRepository

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    """Notification record returned to the client."""

    id: uuid.UUID
    profile_id: uuid.UUID
    opportunity_id: uuid.UUID
    channel: str
    notification_type: str
    idempotency_key: str
    status: str
    content: dict[str, Any]
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime


class NotificationPreferencesRequest(BaseModel):
    """Payload to update user notification preferences."""

    quiet_hours_start: int = Field(default=22, ge=0, le=23)
    quiet_hours_end: int = Field(default=8, ge=0, le=23)
    min_score_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    email_notifications: bool = Field(default=True)


class NotificationPreferencesResponse(BaseModel):
    """Notification preferences for a user."""

    user_id: uuid.UUID
    quiet_hours_start: int
    quiet_hours_end: int
    min_score_threshold: float
    email_notifications: bool
    is_currently_quiet_hours: bool


@router.get("/{user_id}", response_model=list[NotificationResponse])
async def list_user_notifications(
    user_id: uuid.UUID,
    status_filter: str | None = Query(None, alias="status"),
    channel: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
) -> list[NotificationResponse]:
    """
    List notifications for a user profile, ordered by creation date descending.
    """
    profile = await ProfileRepository.get_by_user_id(db, user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile not found for user {user_id}",
        )

    notif_repo = NotificationRepository(db)
    notifications = await notif_repo.list_for_profile(
        profile_id=profile.id,
        status=status_filter,
        channel=channel,
        limit=limit,
    )

    return [
        NotificationResponse(
            id=n.id,
            profile_id=n.profile_id,
            opportunity_id=n.opportunity_id,
            channel=n.channel,
            notification_type=n.notification_type,
            idempotency_key=n.idempotency_key,
            status=n.status,
            content=n.content or {},
            scheduled_at=n.scheduled_at,
            sent_at=n.sent_at,
            created_at=n.created_at,
        )
        for n in notifications
    ]


@router.get("/{user_id}/preferences", response_model=NotificationPreferencesResponse)
async def get_notification_preferences(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> NotificationPreferencesResponse:
    """
    Retrieve notification preferences (quiet hours, thresholds) for a user.
    """
    from notifications.quiet_hours import is_in_quiet_hours

    profile = await ProfileRepository.get_by_user_id(db, user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile not found for user {user_id}",
        )

    constraints = profile.constraints or {}
    notif_config = constraints.get("notifications", {})
    quiet_start = notif_config.get("quiet_hours_start", 22)
    quiet_end = notif_config.get("quiet_hours_end", 8)
    min_score = notif_config.get("min_score_threshold", 0.65)
    email_enabled = notif_config.get("email_notifications", True)

    in_quiet = is_in_quiet_hours(datetime.now(UTC), quiet_start=quiet_start, quiet_end=quiet_end)

    return NotificationPreferencesResponse(
        user_id=user_id,
        quiet_hours_start=quiet_start,
        quiet_hours_end=quiet_end,
        min_score_threshold=min_score,
        email_notifications=email_enabled,
        is_currently_quiet_hours=in_quiet,
    )


@router.put("/{user_id}/preferences", response_model=NotificationPreferencesResponse)
async def update_notification_preferences(
    user_id: uuid.UUID,
    payload: NotificationPreferencesRequest,
    db: AsyncSession = Depends(get_db_session),
) -> NotificationPreferencesResponse:
    """
    Update quiet hours and alert threshold preferences.
    """
    from notifications.quiet_hours import is_in_quiet_hours

    profile = await ProfileRepository.get_by_user_id(db, user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile not found for user {user_id}",
        )

    constraints = dict(profile.constraints or {})
    constraints["notifications"] = {
        "quiet_hours_start": payload.quiet_hours_start,
        "quiet_hours_end": payload.quiet_hours_end,
        "min_score_threshold": payload.min_score_threshold,
        "email_notifications": payload.email_notifications,
    }
    profile.constraints = constraints
    await db.commit()

    in_quiet = is_in_quiet_hours(
        datetime.now(UTC),
        quiet_start=payload.quiet_hours_start,
        quiet_end=payload.quiet_hours_end,
    )

    return NotificationPreferencesResponse(
        user_id=user_id,
        quiet_hours_start=payload.quiet_hours_start,
        quiet_hours_end=payload.quiet_hours_end,
        min_score_threshold=payload.min_score_threshold,
        email_notifications=payload.email_notifications,
        is_currently_quiet_hours=in_quiet,
    )


@router.post("/{user_id}/test", status_code=status.HTTP_200_OK)
async def trigger_test_notification(
    user_id: uuid.UUID,
    force_immediate: bool = Query(True),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Sends a test notification for a user profile to verify delivery and templates.
    """
    from notifications.dispatcher import NotificationDispatcher
    from storage.models.match_score import MatchScore
    from storage.repositories.eligibility_repository import EligibilityRepository

    profile = await ProfileRepository.get_by_user_id(db, user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile for user {user_id} not found.",
        )

    opportunities = await OpportunityRepository.list_opportunities(db, limit=1)

    if not opportunities:
        return {
            "status": "skipped",
            "reason": "No opportunities exist in database to generate a notification from.",
        }

    opp = opportunities[0]
    match_repo = MatchRepository(db)
    elig_repo = EligibilityRepository(db)

    match_score = await match_repo.get_by_pair(opp.id, profile.id)
    elig = await elig_repo.get_by_pair(opp.id, profile.id)

    if not match_score:
        match_score = MatchScore(
            opportunity_id=opp.id,
            profile_id=profile.id,
            final_score=0.88,
            eligibility_score=1.0,
            feature_overlap_score=0.85,
            semantic_similarity_score=0.80,
            explanation="Test Notification: Excellent match based on your skills.",
            scored_at=datetime.now(UTC),
        )

    # Allow testing outside quiet hours when force_immediate is True
    test_now = datetime(2026, 9, 11, 12, 0, 0, tzinfo=UTC) if force_immediate else datetime.now(UTC)

    dispatcher = NotificationDispatcher(db)
    notification = await dispatcher.dispatch_immediate_match(
        profile=profile,
        opportunity=opp,
        match_score=match_score,
        eligibility=elig or type("EligMock", (), {"state": "ELIGIBLE"})(),
        min_score_threshold=0.0,
        as_of=test_now,
    )
    await db.commit()

    if not notification:
        return {
            "status": "deduplicated",
            "message": "Notification already exists for this opportunity version.",
        }

    return {
        "status": "success",
        "notification_id": str(notification.id),
        "channel": notification.channel,
        "delivery_status": notification.status,
        "idempotency_key": notification.idempotency_key,
        "scheduled_at": notification.scheduled_at.isoformat() if notification.scheduled_at else None,
    }
