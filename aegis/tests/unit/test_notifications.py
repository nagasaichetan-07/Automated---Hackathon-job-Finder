"""
Aegis — Unit Tests for Autonomous Notifications (MVP-4)

Covers:
- T-4.1: Repeated scheduler runs never produce duplicate alert for unchanged opportunity (idempotency).
- T-4.2: Daily digest correctly groups multiple opportunities.
- T-4.3: Quiet hours are respected (queued during quiet hours, sent immediately outside).
- T-4.4: Fake email backend passes in CI without external credentials.
- T-4.5: Notification includes all required fields (title, category, score, eligibility, deadline, explanation, URL).
- T-4.6: Re-notification triggers only on meaningful field changes, never on no-op re-crawls.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.schemas.domain import (
    EligibilityDecisionSchema,
    EligibilityState,
    OpportunityCategory,
    OpportunityMode,
    OpportunitySchema,
    ProfileSchema,
)
from notifications.dispatcher import NotificationDispatcher
from notifications.email.backend import FakeEmailBackend, get_email_backend
from notifications.idempotency import (
    compute_digest_idempotency_key,
    compute_idempotency_key,
    compute_opportunity_version_hash,
)
from notifications.quiet_hours import is_in_quiet_hours, next_active_time
from notifications.renderer import render_daily_digest, render_immediate_notification

# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_email_backend() -> FakeEmailBackend:
    backend = FakeEmailBackend()
    backend.clear()
    return backend


@pytest.fixture
def mock_profile() -> ProfileSchema:
    return ProfileSchema(
        id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        education_level="B.Tech",
        graduation_year=2026,
        branch="Computer Science",
        skills=["Python", "React", "FastAPI"],
        preferred_locations=["Remote"],
        opportunity_types=[OpportunityCategory.HACKATHON, OpportunityCategory.INTERNSHIP],
        interests=["AI", "Open Source"],
        constraints={"notifications": {"quiet_hours_start": 22, "quiet_hours_end": 8}},
        resume_confirmed=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_opportunity() -> OpportunitySchema:
    return OpportunitySchema(
        id=uuid.UUID("20000000-0000-0000-0000-000000000001"),
        source_id=uuid.UUID("30000000-0000-0000-0000-000000000001"),
        external_id="opp-2025-001",
        title="Global AI Hackathon 2025",
        category=OpportunityCategory.HACKATHON,
        organizer="OpenAI Community",
        url="https://example.org/hackathon-2025",
        description="Build state-of-the-art AI agents.",
        mode=OpportunityMode.REMOTE,
        location=None,
        registration_deadline=datetime.now(UTC) + timedelta(days=30),
        skills_themes=["Python", "Machine Learning"],
        collected_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_match_score() -> MagicMock:
    m = MagicMock()
    m.final_score = 0.88
    m.explanation = "Eligible: Registration active. High overlap with Python, React."
    return m


@pytest.fixture
def mock_eligibility() -> EligibilityDecisionSchema:
    return EligibilityDecisionSchema(
        id=uuid.UUID("50000000-0000-0000-0000-000000000001"),
        opportunity_id=uuid.UUID("20000000-0000-0000-0000-000000000001"),
        profile_id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
        state=EligibilityState.ELIGIBLE,
        confidence=0.95,
        evidence={"deadline": "Active"},
        rule_results={"deadline": {"status": "PASS", "reason": "Registration is open"}},
        evaluated_at=datetime.now(UTC),
    )


# ===========================================================================
# T-4.5: AC-4.5 Notification Field Completeness
# ===========================================================================

class TestNotificationRendererCompleteness:
    """Verifies that every rendered notification contains all AC-4.5 mandatory fields."""

    def test_immediate_notification_contains_all_required_fields(
        self,
        mock_opportunity: OpportunitySchema,
        mock_match_score: MagicMock,
        mock_eligibility: EligibilityDecisionSchema,
    ) -> None:
        """AC-4.5: title, category, match score, eligibility state, deadline, explanation, URL."""
        rendered = render_immediate_notification(
            opportunity=mock_opportunity,
            match_score=mock_match_score,
            eligibility_decision=mock_eligibility,
        )

        # Verify key metadata
        assert rendered["title"] == mock_opportunity.title
        assert rendered["category"] == "hackathon"
        assert rendered["match_score"] == 0.88
        assert rendered["eligibility_state"] == "ELIGIBLE"
        assert rendered["source_url"] == str(mock_opportunity.url)
        assert "deadline" in rendered and rendered["deadline"] != ""
        assert rendered["explanation"] == mock_match_score.explanation

        # Verify plain text body contains all required facts
        text = rendered["text_body"]
        assert mock_opportunity.title in text
        assert "88%" in text
        assert "ELIGIBLE" in text
        assert str(mock_opportunity.url) in text
        assert mock_match_score.explanation in text

        # Verify HTML body contains all required facts
        html = rendered["html_body"]
        assert mock_opportunity.title in html
        assert "88%" in html
        assert "ELIGIBLE" in html
        assert str(mock_opportunity.url) in html
        assert mock_match_score.explanation in html

    def test_daily_digest_renders_grouped_items(self) -> None:
        """AC-4.1, AC-4.5: Daily digest contains multiple items with individual facts."""
        items = [
            {
                "title": "AI Hackathon",
                "category": "hackathon",
                "match_score": 0.90,
                "eligibility_state": "ELIGIBLE",
                "deadline": "November 20, 2025",
                "explanation": "Matches Python.",
                "source_url": "https://example.com/1",
            },
            {
                "title": "Data Science Internship",
                "category": "internship",
                "match_score": 0.82,
                "eligibility_state": "ELIGIBLE",
                "deadline": "December 15, 2025",
                "explanation": "Matches SQL, Pandas.",
                "source_url": "https://example.com/2",
            },
        ]
        rendered = render_daily_digest(items, user_name="Alex")
        assert rendered["item_count"] == 2
        assert "AI Hackathon" in rendered["text_body"]
        assert "Data Science Internship" in rendered["text_body"]
        assert "90%" in rendered["text_body"]
        assert "82%" in rendered["text_body"]
        assert "AI Hackathon" in rendered["html_body"]


# ===========================================================================
# T-4.4: AC-4.6 Fake Email Backend
# ===========================================================================

class TestFakeEmailBackend:
    """Verifies fake email backend delivers in CI without real credentials."""

    def test_fake_email_captures_without_network(self, fake_email_backend: FakeEmailBackend) -> None:
        success = fake_email_backend.send_email(
            to_email="student@university.edu",
            subject="Test Subject",
            html_body="<p>Test HTML</p>",
            text_body="Test Plain Text",
        )
        assert success is True
        assert fake_email_backend.count == 1
        last = fake_email_backend.sent_emails[0]
        assert last["to"] == "student@university.edu"
        assert last["subject"] == "Test Subject"
        assert "Test HTML" in last["html_body"]
        assert "Test Plain Text" in last["text_body"]

    def test_factory_returns_fake_backend_in_test_mode(self) -> None:
        backend = get_email_backend()
        assert isinstance(backend, FakeEmailBackend)


# ===========================================================================
# T-4.3: AC-4.4 Quiet Hours Evaluation
# ===========================================================================

class TestQuietHoursEnforcement:
    """Verifies quiet hours (default 22:00 to 08:00) deferral and scheduling."""

    def test_active_during_daytime(self) -> None:
        """14:00 UTC should NOT be in quiet hours."""
        midday = datetime(2026, 9, 11, 14, 0, 0, tzinfo=UTC)
        assert is_in_quiet_hours(midday, quiet_start=22, quiet_end=8) is False

    def test_quiet_late_night(self) -> None:
        """23:30 UTC falls inside 22:00-08:00 window."""
        late_night = datetime(2026, 9, 11, 23, 30, 0, tzinfo=UTC)
        assert is_in_quiet_hours(late_night, quiet_start=22, quiet_end=8) is True

    def test_quiet_early_morning(self) -> None:
        """04:15 UTC falls inside 22:00-08:00 window."""
        early_morning = datetime(2026, 9, 11, 4, 15, 0, tzinfo=UTC)
        assert is_in_quiet_hours(early_morning, quiet_start=22, quiet_end=8) is True

    def test_exact_quiet_end_is_active(self) -> None:
        """08:00 UTC is exactly when quiet hours end -> active."""
        morning = datetime(2026, 9, 11, 8, 0, 0, tzinfo=UTC)
        assert is_in_quiet_hours(morning, quiet_start=22, quiet_end=8) is False

    def test_next_active_time_from_late_night(self) -> None:
        """At 23:00 on Sept 11, next active time should be 08:00 on Sept 12."""
        late_night = datetime(2026, 9, 11, 23, 0, 0, tzinfo=UTC)
        target = next_active_time(late_night, quiet_start=22, quiet_end=8)
        assert target.year == 2026
        assert target.month == 9
        assert target.day == 12
        assert target.hour == 8
        assert target.minute == 0

    def test_next_active_time_from_early_morning(self) -> None:
        """At 05:00 on Sept 11, next active time should be 08:00 on Sept 11 (same day)."""
        early_morning = datetime(2026, 9, 11, 5, 0, 0, tzinfo=UTC)
        target = next_active_time(early_morning, quiet_start=22, quiet_end=8)
        assert target.day == 11
        assert target.hour == 8


# ===========================================================================
# T-4.1 & T-4.6: AC-4.2 Idempotency & AC-4.3 Meaningful Versioning
# ===========================================================================

class TestIdempotencyAndVersioning:
    """Verifies stable SHA-256 key and re-notification only on meaningful field changes."""

    def test_stable_idempotency_key_formula(self) -> None:
        """Idempotency key strictly equals SHA256(user_id + opportunity_id + version_hash)."""
        import hashlib
        user_id = "user-123"
        opp_id = "opp-456"
        version_hash = "abc123"
        expected = hashlib.sha256(f"{user_id}:{opp_id}:{version_hash}".encode()).hexdigest()

        actual = compute_idempotency_key(user_id, opp_id, version_hash)
        assert actual == expected

    def test_no_op_re_crawl_produces_identical_version_hash(
        self,
        mock_opportunity: OpportunitySchema,
    ) -> None:
        """AC-4.3: Changing crawl timestamp or internal id does not change version hash."""
        hash1 = compute_opportunity_version_hash(mock_opportunity)

        # Simulate re-crawl: updated_at changed, but title/mode/deadline identical
        opp2 = mock_opportunity.model_copy(
            update={"updated_at": datetime.now(UTC) + timedelta(hours=5)}
        )
        hash2 = compute_opportunity_version_hash(opp2)

        assert hash1 == hash2

    def test_meaningful_deadline_change_produces_new_version_hash(
        self,
        mock_opportunity: OpportunitySchema,
    ) -> None:
        """AC-4.3: Changing deadline produces a new version hash (re-notification eligible)."""
        hash1 = compute_opportunity_version_hash(mock_opportunity)

        # Extended deadline
        assert mock_opportunity.registration_deadline is not None
        new_deadline = mock_opportunity.registration_deadline + timedelta(days=14)
        opp_extended = mock_opportunity.model_copy(
            update={"registration_deadline": new_deadline}
        )
        hash2 = compute_opportunity_version_hash(opp_extended)

        assert hash1 != hash2

    def test_meaningful_mode_change_produces_new_version_hash(
        self,
        mock_opportunity: OpportunitySchema,
    ) -> None:
        """AC-4.3: Remote vs Onsite mode change triggers new hash."""
        hash1 = compute_opportunity_version_hash(mock_opportunity)
        opp_onsite = mock_opportunity.model_copy(update={"mode": OpportunityMode.ONSITE})
        hash2 = compute_opportunity_version_hash(opp_onsite)

        assert hash1 != hash2

    def test_digest_idempotency_key_is_per_day(self) -> None:
        """Daily digest key includes date string to prevent multi-digest same day."""
        key_today = compute_digest_idempotency_key("user-1", "2026-09-11")
        key_today_repeat = compute_digest_idempotency_key("user-1", "2026-09-11")
        key_tomorrow = compute_digest_idempotency_key("user-1", "2026-09-12")

        assert key_today == key_today_repeat
        assert key_today != key_tomorrow


# ===========================================================================
# Dispatcher Integration Tests (T-4.1, T-4.3)
# ===========================================================================

class TestNotificationDispatcher:
    """Verifies end-to-end dispatching logic, quiet hours deferral, and dedup."""

    @pytest.mark.asyncio
    async def test_immediate_dispatch_outside_quiet_hours_sends_email(
        self,
        mock_profile: ProfileSchema,
        mock_opportunity: OpportunitySchema,
        mock_match_score: MagicMock,
        mock_eligibility: EligibilityDecisionSchema,
        fake_email_backend: FakeEmailBackend,
    ) -> None:
        """During active hours, notification status='sent' and email is delivered."""
        mock_session = AsyncMock()
        dispatcher = NotificationDispatcher(mock_session, email_backend=fake_email_backend)

        # Mock repository to simulate fresh notification
        dispatcher.repo = MagicMock()
        dispatcher.repo.get_by_idempotency_key = AsyncMock(return_value=None)
        dispatcher.repo.create_notification = AsyncMock()
        mock_notif = MagicMock(status="sent", idempotency_key="key-123")
        dispatcher.repo.create_notification.return_value = mock_notif

        # Daytime: 14:00 UTC
        daytime = datetime(2026, 9, 11, 14, 0, 0, tzinfo=UTC)

        result = await dispatcher.dispatch_immediate_match(
            profile=mock_profile,
            opportunity=mock_opportunity,
            match_score=mock_match_score,
            eligibility=mock_eligibility,
            as_of=daytime,
        )

        assert result is not None
        assert result.status == "sent"
        assert fake_email_backend.count == 1
        assert "Global AI Hackathon 2025" in fake_email_backend.sent_emails[0]["subject"]

    @pytest.mark.asyncio
    async def test_immediate_dispatch_during_quiet_hours_queues_notification(
        self,
        mock_profile: ProfileSchema,
        mock_opportunity: OpportunitySchema,
        mock_match_score: MagicMock,
        mock_eligibility: EligibilityDecisionSchema,
        fake_email_backend: FakeEmailBackend,
    ) -> None:
        """AC-4.4: During quiet hours (23:00 UTC), status='pending' and email is NOT sent immediately."""
        mock_session = AsyncMock()
        dispatcher = NotificationDispatcher(mock_session, email_backend=fake_email_backend)

        dispatcher.repo = MagicMock()
        dispatcher.repo.get_by_idempotency_key = AsyncMock(return_value=None)
        dispatcher.repo.create_notification = AsyncMock()
        mock_notif = MagicMock(status="pending", scheduled_at=datetime(2026, 9, 12, 8, 0, 0, tzinfo=UTC))
        dispatcher.repo.create_notification.return_value = mock_notif

        # Night time: 23:00 UTC
        night_time = datetime(2026, 9, 11, 23, 0, 0, tzinfo=UTC)

        result = await dispatcher.dispatch_immediate_match(
            profile=mock_profile,
            opportunity=mock_opportunity,
            match_score=mock_match_score,
            eligibility=mock_eligibility,
            as_of=night_time,
        )

        assert result is not None
        assert result.status == "pending"
        # Zero emails sent during quiet hours!
        assert fake_email_backend.count == 0

    @pytest.mark.asyncio
    async def test_repeated_run_skips_when_idempotency_key_exists(
        self,
        mock_profile: ProfileSchema,
        mock_opportunity: OpportunitySchema,
        mock_match_score: MagicMock,
        mock_eligibility: EligibilityDecisionSchema,
        fake_email_backend: FakeEmailBackend,
    ) -> None:
        """T-4.1: Repeated scheduler run skips if idempotency key already exists."""
        mock_session = AsyncMock()
        dispatcher = NotificationDispatcher(mock_session, email_backend=fake_email_backend)

        # Simulate existing notification record in database
        dispatcher.repo = MagicMock()
        dispatcher.repo.get_by_idempotency_key = AsyncMock(
            return_value=MagicMock(id=uuid.uuid4(), status="sent")
        )

        result = await dispatcher.dispatch_immediate_match(
            profile=mock_profile,
            opportunity=mock_opportunity,
            match_score=mock_match_score,
            eligibility=mock_eligibility,
        )

        # Skips entirely, zero duplicates, zero emails
        assert result is None
        assert fake_email_backend.count == 0

    @pytest.mark.asyncio
    async def test_ineligible_match_never_notifies(
        self,
        mock_profile: ProfileSchema,
        mock_opportunity: OpportunitySchema,
        fake_email_backend: FakeEmailBackend,
    ) -> None:
        """Disqualified opportunity must never generate an alert."""
        mock_session = AsyncMock()
        dispatcher = NotificationDispatcher(mock_session, email_backend=fake_email_backend)

        ineligible_decision = MagicMock(state=EligibilityState.INELIGIBLE)
        ineligible_score = MagicMock(final_score=0.0)

        result = await dispatcher.dispatch_immediate_match(
            profile=mock_profile,
            opportunity=mock_opportunity,
            match_score=ineligible_score,
            eligibility=ineligible_decision,
        )

        assert result is None
        assert fake_email_backend.count == 0

    @pytest.mark.asyncio
    async def test_low_score_match_never_notifies(
        self,
        mock_profile: ProfileSchema,
        mock_opportunity: OpportunitySchema,
        mock_eligibility: EligibilityDecisionSchema,
        fake_email_backend: FakeEmailBackend,
    ) -> None:
        """Matches below threshold (e.g. 0.35 < 0.65) must not trigger immediate alerts."""
        mock_session = AsyncMock()
        dispatcher = NotificationDispatcher(mock_session, email_backend=fake_email_backend)

        low_score = MagicMock(final_score=0.35)

        result = await dispatcher.dispatch_immediate_match(
            profile=mock_profile,
            opportunity=mock_opportunity,
            match_score=low_score,
            eligibility=mock_eligibility,
            min_score_threshold=0.65,
        )

        assert result is None
        assert fake_email_backend.count == 0


# ===========================================================================
# Hackathon Visibility Filter Integration Tests for Notifications
# ===========================================================================

class TestHackathonVisibilityNotificationIntegration:
    """Verifies that NotificationDispatcher enforces Hackathon Visibility Filter."""

    @pytest.mark.asyncio
    async def test_immediate_dispatch_skips_invisible_hackathon(
        self,
        mock_profile: ProfileSchema,
        mock_match_score: MagicMock,
        mock_eligibility: EligibilityDecisionSchema,
        fake_email_backend: FakeEmailBackend,
    ) -> None:
        """In-person Bangalore hackathon must be skipped by immediate dispatcher."""
        mock_session = AsyncMock()
        dispatcher = NotificationDispatcher(mock_session, email_backend=fake_email_backend)

        bangalore_hackathon = OpportunitySchema(
            id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            external_id="opp-blr-001",
            title="Bangalore Offline Hackathon",
            category=OpportunityCategory.HACKATHON,
            url="https://example.org/hackathon-blr",
            mode=OpportunityMode.ONSITE,
            location="Bangalore, Karnataka",
            registration_deadline=datetime.now(UTC) + timedelta(days=10),
            collected_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        result = await dispatcher.dispatch_immediate_match(
            profile=mock_profile,
            opportunity=bangalore_hackathon,
            match_score=mock_match_score,
            eligibility=mock_eligibility,
        )

        assert result is None
        assert fake_email_backend.count == 0

    @pytest.mark.asyncio
    async def test_daily_digest_filters_out_invisible_hackathons(
        self,
        mock_profile: ProfileSchema,
        fake_email_backend: FakeEmailBackend,
    ) -> None:
        """Daily digest skips items failing hackathon visibility filter."""
        mock_session = AsyncMock()
        dispatcher = NotificationDispatcher(mock_session, email_backend=fake_email_backend)

        invisible_item = {
            "title": "Expired Online Hackathon",
            "category": "hackathon",
            "mode": "remote",
            "registration_deadline": (datetime.now(UTC) - timedelta(days=5)).isoformat(),
            "match_score": 0.90,
            "eligibility_state": "ELIGIBLE",
            "source_url": "https://example.com/expired",
        }

        result = await dispatcher.dispatch_daily_digest(
            profile=mock_profile,
            top_items=[invisible_item],
        )

        assert result is None
        assert fake_email_backend.count == 0

