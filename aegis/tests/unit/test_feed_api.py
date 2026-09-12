"""
Aegis — Feed API Router Test Suite (Phase 5)

Tests the feed API endpoints:
- GET /api/v1/feed/{user_id}: ranked feed retrieval
- POST /api/v1/feed/{user_id}/evaluate: on-demand evaluation trigger
- POST /api/v1/feed/{user_id}/feedback: user feedback submission
- 404 handling for missing profiles

These tests mock the DB session and repository layer to run without a live database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apps.api.main import app
from httpx import ASGITransport, AsyncClient
from storage.database import get_db_session

# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

MOCK_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
MOCK_PROFILE_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
MOCK_OPP_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")


def _mock_profile():
    """Create a mock profile ORM-like object."""
    profile = MagicMock()
    profile.id = MOCK_PROFILE_ID
    profile.user_id = MOCK_USER_ID
    profile.education_level = "B.Tech"
    profile.graduation_year = 2026
    profile.branch = "Computer Science"
    profile.skills = ["Python", "React"]
    profile.preferred_locations = ["Remote"]
    profile.opportunity_types = ["hackathon"]
    profile.interests = ["AI"]
    profile.constraints = {}
    profile.resume_raw_text = None
    profile.resume_extracted = None
    profile.resume_confirmed = False
    profile.resume_evidence = None
    profile.created_at = datetime.now(UTC)
    profile.updated_at = datetime.now(UTC)
    return profile


def _mock_match_score():
    """Create a mock match score ORM-like object."""
    m = MagicMock()
    m.opportunity_id = MOCK_OPP_ID
    m.profile_id = MOCK_PROFILE_ID
    m.final_score = 0.85
    m.explanation = "Eligible: Meets all criteria. Matches Python, React."
    m.score_breakdown = {
        "eligibility": {"state": "ELIGIBLE", "score": 1.0},
        "disqualified": False,
    }
    m.user_feedback = None
    return m


def _mock_opportunity():
    """Create a mock opportunity ORM-like object."""
    opp = MagicMock()
    opp.id = MOCK_OPP_ID
    opp.title = "AI Hackathon 2026"
    opp.category = "hackathon"
    opp.organizer = "Test Org"
    opp.url = "https://example.com/hackathon"
    opp.description = "Build AI agents."
    opp.location = None
    opp.mode = "remote"
    opp.registration_deadline = datetime.now(UTC) + timedelta(days=30)
    return opp


def _mock_eligibility():
    """Create a mock eligibility ORM-like object."""
    e = MagicMock()
    e.state = "ELIGIBLE"
    return e


# ---------------------------------------------------------------------------
# DB Session Override
# ---------------------------------------------------------------------------

async def _override_get_db():
    """Provide a mock async session."""
    session = AsyncMock()
    yield session


# Apply override for all tests in this module
app.dependency_overrides[get_db_session] = _override_get_db


# ===========================================================================
# GET /api/v1/feed/{user_id}
# ===========================================================================

class TestGetUserFeed:
    """Tests for feed retrieval endpoint."""

    @pytest.mark.asyncio
    async def test_feed_returns_404_for_missing_profile(self) -> None:
        """Should return 404 when no profile exists for user_id."""
        with patch(
            "apps.api.routers.feed.ProfileRepository"
        ) as MockProfileRepo:
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=None)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/api/v1/feed/{uuid.uuid4()}")
                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_feed_returns_list_with_existing_matches(self) -> None:
        """Should return ranked feed items when matches exist."""
        with (
            patch("apps.api.routers.feed.ProfileRepository") as MockProfileRepo,
            patch("apps.api.routers.feed.MatchRepository") as MockMatchRepo,
            patch("apps.api.routers.feed.OpportunityRepository") as MockOppRepo,
            patch("apps.api.routers.feed.EligibilityRepository") as MockEligRepo,
        ):
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=_mock_profile())
            MockMatchRepo.return_value.get_ranked_matches = AsyncMock(return_value=[_mock_match_score()])
            MockOppRepo.get_by_id = MockOppRepo.return_value.get_by_id = AsyncMock(return_value=_mock_opportunity())
            MockEligRepo.return_value.get_by_pair = AsyncMock(return_value=_mock_eligibility())

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/api/v1/feed/{MOCK_USER_ID}")
                assert response.status_code == 200
                data = response.json()
                assert isinstance(data, list)
                assert len(data) >= 1
                item = data[0]
                assert "opportunity_id" in item
                assert "final_score" in item
                assert "eligibility_state" in item
                assert "explanation" in item
                assert "score_breakdown" in item

    @pytest.mark.asyncio
    async def test_feed_response_schema_fields(self) -> None:
        """Feed items should contain all expected response fields."""
        with (
            patch("apps.api.routers.feed.ProfileRepository") as MockProfileRepo,
            patch("apps.api.routers.feed.MatchRepository") as MockMatchRepo,
            patch("apps.api.routers.feed.OpportunityRepository") as MockOppRepo,
            patch("apps.api.routers.feed.EligibilityRepository") as MockEligRepo,
        ):
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=_mock_profile())
            MockMatchRepo.return_value.get_ranked_matches = AsyncMock(return_value=[_mock_match_score()])
            MockOppRepo.get_by_id = MockOppRepo.return_value.get_by_id = AsyncMock(return_value=_mock_opportunity())
            MockEligRepo.return_value.get_by_pair = AsyncMock(return_value=_mock_eligibility())

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/api/v1/feed/{MOCK_USER_ID}")
                assert response.status_code == 200
                data = response.json()
                item = data[0]
                expected_fields = {
                    "opportunity_id", "title", "category", "organizer",
                    "url", "description", "location", "mode",
                    "registration_deadline", "final_score",
                    "eligibility_state", "explanation",
                    "score_breakdown", "user_feedback",
                }
                assert expected_fields.issubset(set(item.keys()))


# ===========================================================================
# POST /api/v1/feed/{user_id}/evaluate
# ===========================================================================

class TestEvaluateOpportunities:
    """Tests for on-demand evaluation endpoint."""

    @pytest.mark.asyncio
    async def test_evaluate_returns_404_for_missing_profile(self) -> None:
        """Should return 404 when no profile exists for user_id."""
        with patch("apps.api.routers.feed.ProfileRepository") as MockProfileRepo:
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=None)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(f"/api/v1/feed/{uuid.uuid4()}/evaluate")
                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_evaluate_returns_zero_when_no_opportunities(self) -> None:
        """Should return evaluated_count=0 when no opportunities exist."""
        with (
            patch("apps.api.routers.feed.ProfileRepository") as MockProfileRepo,
            patch("apps.api.routers.feed.OpportunityRepository") as MockOppRepo,
        ):
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=_mock_profile())
            MockOppRepo.list_opportunities = MockOppRepo.return_value.list_opportunities = AsyncMock(return_value=[])

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(f"/api/v1/feed/{MOCK_USER_ID}/evaluate")
                assert response.status_code == 200
                data = response.json()
                assert data["evaluated_count"] == 0


# ===========================================================================
# POST /api/v1/feed/{user_id}/feedback
# ===========================================================================

class TestUserFeedback:
    """Tests for user feedback submission endpoint."""

    @pytest.mark.asyncio
    async def test_feedback_returns_404_for_missing_profile(self) -> None:
        """Should return 404 when profile is not found."""
        with patch("apps.api.routers.feed.ProfileRepository") as MockProfileRepo:
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=None)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    f"/api/v1/feed/{uuid.uuid4()}/feedback",
                    json={"opportunity_id": str(MOCK_OPP_ID), "feedback": "interested"},
                )
                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_feedback_success(self) -> None:
        """Should return success when feedback is recorded."""
        with (
            patch("apps.api.routers.feed.ProfileRepository") as MockProfileRepo,
            patch("apps.api.routers.feed.MatchRepository") as MockMatchRepo,
        ):
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=_mock_profile())
            MockMatchRepo.return_value.update_feedback = AsyncMock(return_value=True)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    f"/api/v1/feed/{MOCK_USER_ID}/feedback",
                    json={"opportunity_id": str(MOCK_OPP_ID), "feedback": "interested"},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["user_feedback"] == "interested"

    @pytest.mark.asyncio
    async def test_feedback_invalid_value_rejected(self) -> None:
        """Should return 422 for invalid feedback value."""
        with patch("apps.api.routers.feed.ProfileRepository") as MockProfileRepo:
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=_mock_profile())

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    f"/api/v1/feed/{MOCK_USER_ID}/feedback",
                    json={"opportunity_id": str(MOCK_OPP_ID), "feedback": "invalid_value"},
                )
                assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_feedback_returns_404_when_match_not_found(self) -> None:
        """Should return 404 when no match score exists for the opportunity-profile pair."""
        with (
            patch("apps.api.routers.feed.ProfileRepository") as MockProfileRepo,
            patch("apps.api.routers.feed.MatchRepository") as MockMatchRepo,
        ):
            MockProfileRepo.get_by_user_id = MockProfileRepo.return_value.get_by_user_id = AsyncMock(return_value=_mock_profile())
            MockMatchRepo.return_value.update_feedback = AsyncMock(return_value=False)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    f"/api/v1/feed/{MOCK_USER_ID}/feedback",
                    json={"opportunity_id": str(MOCK_OPP_ID), "feedback": "dismissed"},
                )
                assert response.status_code == 404
