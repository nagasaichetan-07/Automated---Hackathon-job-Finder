"""
Aegis — Unit Tests for Hackathon Visibility Filter

Validates:
1. Online hackathon with future deadline (SHOULD SHOW - True)
2. In-person Hyderabad hackathon (SHOULD SHOW - True)
3. In-person Bangalore hackathon (SHOULD NOT SHOW - False)
4. Online hackathon whose deadline already passed (SHOULD NOT SHOW - False)
5. Hackathon with missing/UNKNOWN location and in-person mode (SHOULD NOT SHOW - False)
6. Independent Condition A & Condition B tests
7. Non-hackathon pass-through behavior
"""

import uuid
from datetime import UTC, datetime, timedelta
import pytest

from core.schemas.domain import OpportunityCategory, OpportunityMode, OpportunitySchema
from opportunity.filters import (
    is_hackathon_location_valid,
    is_hackathon_status_valid,
    is_hackathon_visible,
    visible_hackathon_filter,
)

NOW = datetime(2026, 9, 12, 12, 0, 0, tzinfo=UTC)


def make_hackathon(
    title: str = "Test Hackathon",
    mode: OpportunityMode | str = OpportunityMode.REMOTE,
    location: str | None = "Online / Virtual",
    reg_deadline: datetime | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    category: OpportunityCategory = OpportunityCategory.HACKATHON,
) -> OpportunitySchema:
    return OpportunitySchema(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        external_id=f"test-{uuid.uuid4()}",
        title=title,
        category=category,
        url="https://example.com/hackathon",
        mode=mode if isinstance(mode, OpportunityMode) else None,
        location=location,
        registration_deadline=reg_deadline,
        start_date=start_date,
        end_date=end_date,
        collected_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


# ---------------------------------------------------------------------------
# The 5 Required Test Cases
# ---------------------------------------------------------------------------


def test_1_online_hackathon_with_future_deadline_should_show():
    """Test 1: Online hackathon with a future deadline -> SHOULD SHOW (True)."""
    opp = make_hackathon(
        title="Global Online Hackathon 2026",
        mode=OpportunityMode.REMOTE,
        location="Online / Virtual",
        reg_deadline=NOW + timedelta(days=10),
    )
    assert is_hackathon_status_valid(opp, now=NOW) is True
    assert is_hackathon_location_valid(opp) is True
    assert is_hackathon_visible(opp, now=NOW) is True


def test_2_in_person_hyderabad_hackathon_should_show():
    """Test 2: In-person Hyderabad hackathon -> SHOULD SHOW (True)."""
    opp_variants = [
        make_hackathon(
            title="Hyderabad DevFest Hack",
            mode=OpportunityMode.ONSITE,
            location="Hyderabad, Telangana",
            reg_deadline=NOW + timedelta(days=5),
        ),
        make_hackathon(
            title="CBIT Hyderabad Regional",
            mode=OpportunityMode.HYBRID,
            location="Hyderabad, India",
            reg_deadline=NOW + timedelta(days=7),
        ),
    ]

    for opp in opp_variants:
        assert is_hackathon_status_valid(opp, now=NOW) is True
        assert is_hackathon_location_valid(opp) is True
        assert is_hackathon_visible(opp, now=NOW) is True


def test_3_in_person_bangalore_hackathon_should_not_show():
    """Test 3: In-person Bangalore hackathon -> SHOULD NOT SHOW (False)."""
    opp = make_hackathon(
        title="Bangalore Tech Challenge",
        mode=OpportunityMode.ONSITE,
        location="Bangalore, Karnataka",
        reg_deadline=NOW + timedelta(days=5),
    )
    assert is_hackathon_status_valid(opp, now=NOW) is True
    assert is_hackathon_location_valid(opp) is False
    assert is_hackathon_visible(opp, now=NOW) is False


def test_4_online_hackathon_deadline_passed_should_not_show():
    """Test 4: Online hackathon whose deadline already passed -> SHOULD NOT SHOW (False)."""
    opp = make_hackathon(
        title="Past Online Assessment",
        mode=OpportunityMode.REMOTE,
        location="Online / Virtual",
        reg_deadline=NOW - timedelta(days=2),
    )
    assert is_hackathon_status_valid(opp, now=NOW) is False
    assert is_hackathon_location_valid(opp) is True
    assert is_hackathon_visible(opp, now=NOW) is False


def test_5_missing_unknown_location_in_person_mode_should_not_show():
    """Test 5: Hackathon with missing/UNKNOWN location and in-person mode -> SHOULD NOT SHOW (False)."""
    opp_missing = make_hackathon(
        title="Unknown Location Hackathon",
        mode=OpportunityMode.ONSITE,
        location=None,
        reg_deadline=NOW + timedelta(days=5),
    )
    opp_unknown = make_hackathon(
        title="Unknown Location Hackathon 2",
        mode=OpportunityMode.HYBRID,
        location="UNKNOWN",
        reg_deadline=NOW + timedelta(days=5),
    )

    for opp in [opp_missing, opp_unknown]:
        assert is_hackathon_location_valid(opp) is False
        assert is_hackathon_visible(opp, now=NOW) is False


# ---------------------------------------------------------------------------
# Additional Verification & Edge Cases
# ---------------------------------------------------------------------------


def test_non_hackathon_categories_bypass_filter():
    """Jobs and internships are untouched by the hackathon visibility filter."""
    job = make_hackathon(
        title="Senior Python Engineer",
        category=OpportunityCategory.JOB,
        mode=OpportunityMode.ONSITE,
        location="Bangalore, India",
        reg_deadline=NOW - timedelta(days=10),
    )
    internship = make_hackathon(
        title="Data Science Intern",
        category=OpportunityCategory.INTERNSHIP,
        mode=OpportunityMode.ONSITE,
        location="Delhi, India",
    )

    assert is_hackathon_visible(job, now=NOW) is True
    assert is_hackathon_visible(internship, now=NOW) is True


def test_visible_hackathon_filter_helper():
    """Batch list filter returns only valid hackathons + non-hackathons."""
    opp_valid_online = make_hackathon("Valid Online", OpportunityMode.REMOTE, reg_deadline=NOW + timedelta(days=1))
    opp_valid_hyd = make_hackathon("Valid Hyd", OpportunityMode.ONSITE, "Hyderabad", reg_deadline=NOW + timedelta(days=1))
    opp_invalid_blr = make_hackathon("Invalid Blr", OpportunityMode.ONSITE, "Bangalore", reg_deadline=NOW + timedelta(days=1))
    opp_invalid_expired = make_hackathon("Expired Online", OpportunityMode.REMOTE, reg_deadline=NOW - timedelta(days=1))

    items = [opp_valid_online, opp_valid_hyd, opp_invalid_blr, opp_invalid_expired]
    filtered = visible_hackathon_filter(items, now=NOW)

    assert len(filtered) == 2
    assert {o.title for o in filtered} == {"Valid Online", "Valid Hyd"}
