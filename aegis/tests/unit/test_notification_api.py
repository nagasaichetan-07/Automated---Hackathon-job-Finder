"""
Aegis — Unit Tests for Notification API Router (Phase 6)

Tests endpoints:
- GET /api/v1/notifications/{user_id}
- GET /api/v1/notifications/{user_id}/preferences
- PUT /api/v1/notifications/{user_id}/preferences
- POST /api/v1/notifications/{user_id}/test
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apps.api.main import app
from httpx import ASGITransport, AsyncClient
from storage.database import get_db_session

MOCK_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
MOCK_PROFILE_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
MOCK_OPP_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")


def _mock_profile():
    profile = MagicMock()
    profile.id = MOCK_PROFILE_ID
    profile.user_id = MOCK_USER_ID
    profile.constraints = {
        "notifications": {
            "quiet_hours_start": 22,
            "quiet_hours_end": 8,
            "min_score_threshold": 0.65,
            "email_notifications": True,
        }
    }
    return profile


def _mock_notification():
    n = MagicMock()
    n.id = uuid.UUID("40000000-0000-0000-0000-000000000001")
    n.profile_id = MOCK_PROFILE_ID
    n.opportunity_id = MOCK_OPP_ID
    n.channel = "email"
    n.notification_type = "immediate"
    n.idempotency_key = "test-idempotency-key-123456"
    n.status = "sent"
    n.content = {
        "title": "Global AI Hackathon 2025",
        "category": "hackathon",
        "match_score": 0.90,
        "eligibility_state": "ELIGIBLE",
        "deadline": "November 15, 2025",
        "explanation": "High skill overlap.",
        "source_url": "https://example.com/hackathon",
    }
    n.scheduled_at = None
    n.sent_at = datetime.now(UTC)
    n.created_at = datetime.now(UTC)
    return n


async def _override_get_db():
    session = AsyncMock()
    yield session


app.dependency_overrides[get_db_session] = _override_get_db


class TestNotificationAPIEndpoints:
    """Tests for notifications router endpoints."""

    @pytest.mark.asyncio
    async def test_list_notifications_404_for_missing_profile(self) -> None:
        with patch("apps.api.routers.notifications.ProfileRepository") as MockProfileRepo:
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=None)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get(f"/api/v1/notifications/{uuid.uuid4()}")
                assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_list_notifications_success(self) -> None:
        with (
            patch("apps.api.routers.notifications.ProfileRepository") as MockProfileRepo,
            patch("apps.api.routers.notifications.NotificationRepository") as MockNotifRepo,
        ):
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=_mock_profile())
            MockNotifRepo.return_value.list_for_profile = AsyncMock(return_value=[_mock_notification()])

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get(f"/api/v1/notifications/{MOCK_USER_ID}")
                assert res.status_code == 200
                data = res.json()
                assert isinstance(data, list)
                assert len(data) == 1
                assert data[0]["channel"] == "email"
                assert data[0]["status"] == "sent"
                assert data[0]["content"]["title"] == "Global AI Hackathon 2025"

    @pytest.mark.asyncio
    async def test_get_preferences(self) -> None:
        with patch("apps.api.routers.notifications.ProfileRepository") as MockProfileRepo:
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=_mock_profile())

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get(f"/api/v1/notifications/{MOCK_USER_ID}/preferences")
                assert res.status_code == 200
                data = res.json()
                assert data["quiet_hours_start"] == 22
                assert data["quiet_hours_end"] == 8
                assert data["min_score_threshold"] == 0.65
                assert data["email_notifications"] is True
                assert "is_currently_quiet_hours" in data

    @pytest.mark.asyncio
    async def test_update_preferences(self) -> None:
        with patch("apps.api.routers.notifications.ProfileRepository") as MockProfileRepo:
            prof = _mock_profile()
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=prof)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                payload = {
                    "quiet_hours_start": 23,
                    "quiet_hours_end": 7,
                    "min_score_threshold": 0.75,
                    "email_notifications": True,
                }
                res = await client.put(f"/api/v1/notifications/{MOCK_USER_ID}/preferences", json=payload)
                assert res.status_code == 200
                data = res.json()
                assert data["quiet_hours_start"] == 23
                assert data["quiet_hours_end"] == 7
                assert data["min_score_threshold"] == 0.75

    @pytest.mark.asyncio
    async def test_test_notification_trigger_404_when_no_profile(self) -> None:
        with patch("apps.api.routers.notifications.ProfileRepository") as MockProfileRepo:
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=None)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(f"/api/v1/notifications/{uuid.uuid4()}/test")
                assert res.status_code == 404
