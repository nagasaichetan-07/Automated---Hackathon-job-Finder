"""
Aegis — Eligibility Engine Test Suite (Phase 5)

Tests: T-3.1, T-3.2, T-3.3
- Deterministic rules: deadline, degree, graduation year, branch, location, team_size
- Tri-State output: ELIGIBLE, INELIGIBLE, UNKNOWN
- Preservation of UNKNOWN when evidence is insufficient
- Hard exclusion dominance: any failure => INELIGIBLE overrides all passes
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from core.schemas.domain import (
    EligibilityState,
    OpportunityCategory,
    OpportunityMode,
    OpportunitySchema,
    ProfileSchema,
)
from opportunity.eligibility.engine import EligibilityEngine

# ---------------------------------------------------------------------------
# Helpers — Factory Functions
# ---------------------------------------------------------------------------

def _make_profile(**overrides: Any) -> ProfileSchema:
    """Build a minimal valid ProfileSchema for testing."""
    base: dict[str, Any] = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        education_level="B.Tech",
        graduation_year=2026,
        branch="Computer Science",
        skills=["Python", "React", "SQL"],
        preferred_locations=["Remote", "Bangalore"],
        opportunity_types=[OpportunityCategory.HACKATHON, OpportunityCategory.INTERNSHIP],
        interests=["AI", "Web Development"],
        constraints={},
        resume_raw_text=None,
        resume_extracted=None,
        resume_confirmed=False,
        resume_evidence=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    base.update(overrides)
    return ProfileSchema.model_validate(base)


def _make_opportunity(**overrides: Any) -> OpportunitySchema:
    """Build a minimal valid OpportunitySchema for testing."""
    base: dict[str, Any] = dict(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        external_id="test-opp-001",
        title="AI Hackathon 2026",
        category=OpportunityCategory.HACKATHON,
        organizer="Test Org",
        url="https://example.com/hackathon",
        description="Build autonomous AI agents. Open to Bachelor/B.Tech students.",
        registration_deadline=datetime.now(UTC) + timedelta(days=30),
        start_date=None,
        end_date=None,
        location=None,
        mode=OpportunityMode.REMOTE,
        eligibility_text=None,
        team_size_min=None,
        team_size_max=None,
        prize=None,
        skills_themes=["Python", "FastAPI"],
        evidence={},
        content_hash=None,
        published_at=None,
        collected_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    base.update(overrides)
    return OpportunitySchema.model_validate(base)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine() -> EligibilityEngine:
    return EligibilityEngine()


@pytest.fixture
def profile() -> ProfileSchema:
    return _make_profile()


@pytest.fixture
def opportunity() -> OpportunitySchema:
    return _make_opportunity()


# ===========================================================================
# T-3.1: Deterministic Rule Tests
# ===========================================================================

class TestDeadlineRule:
    """Tests for registration deadline eligibility rule."""

    def test_active_deadline_passes(self, engine: EligibilityEngine, profile: ProfileSchema) -> None:
        """Future deadline should produce PASS."""
        opp = _make_opportunity(registration_deadline=datetime.now(UTC) + timedelta(days=10))
        result = engine.evaluate(profile, opp)
        assert result.rule_results["deadline"]["status"] == "PASS"

    def test_expired_deadline_fails(self, engine: EligibilityEngine, profile: ProfileSchema) -> None:
        """Past deadline should produce FAIL and result in INELIGIBLE overall."""
        opp = _make_opportunity(registration_deadline=datetime.now(UTC) - timedelta(days=5))
        result = engine.evaluate(profile, opp)
        assert result.rule_results["deadline"]["status"] == "FAIL"
        assert result.state == EligibilityState.INELIGIBLE

    def test_missing_deadline_is_unknown(self, engine: EligibilityEngine, profile: ProfileSchema) -> None:
        """No deadline specified should produce UNKNOWN for that rule."""
        opp = _make_opportunity(registration_deadline=None)
        result = engine.evaluate(profile, opp)
        assert result.rule_results["deadline"]["status"] == "UNKNOWN"

    def test_deadline_just_passed_is_ineligible(self, engine: EligibilityEngine, profile: ProfileSchema) -> None:
        """Deadline 1 second ago should still be FAIL/INELIGIBLE."""
        expired = datetime.now(UTC) - timedelta(seconds=1)
        opp = _make_opportunity(registration_deadline=expired)
        result = engine.evaluate(profile, opp)
        assert result.rule_results["deadline"]["status"] == "FAIL"
        assert result.state == EligibilityState.INELIGIBLE


class TestDegreeRule:
    """Tests for education degree eligibility rule."""

    def test_bachelor_requirement_met_by_btech(self, engine: EligibilityEngine) -> None:
        """B.Tech student should pass Bachelor requirement."""
        profile = _make_profile(education_level="B.Tech")
        opp = _make_opportunity(description="Open to Bachelor/Undergraduate students.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["degree"]["status"] == "PASS"

    def test_masters_requirement_fails_for_bachelors(self, engine: EligibilityEngine) -> None:
        """Bachelor student should fail a Masters-only requirement."""
        profile = _make_profile(education_level="B.Tech")
        opp = _make_opportunity(description="Requires Master's degree or higher.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["degree"]["status"] == "FAIL"

    def test_phd_requirement_fails_for_bachelors(self, engine: EligibilityEngine) -> None:
        """Bachelor student should fail a PhD-only requirement."""
        profile = _make_profile(education_level="B.Tech")
        opp = _make_opportunity(description="Only PhD candidates may apply.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["degree"]["status"] == "FAIL"

    def test_masters_passes_masters_req(self, engine: EligibilityEngine) -> None:
        """M.Tech student should pass Master's requirement."""
        profile = _make_profile(education_level="M.Tech")
        opp = _make_opportunity(description="Requires Master's degree or higher.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["degree"]["status"] == "PASS"

    def test_no_degree_text_is_unknown(self, engine: EligibilityEngine) -> None:
        """No degree-related text should produce UNKNOWN for degree rule."""
        profile = _make_profile(education_level="B.Tech")
        opp = _make_opportunity(description="Join us for a weekend coding sprint!")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["degree"]["status"] == "UNKNOWN"

    def test_missing_profile_education_is_unknown(self, engine: EligibilityEngine) -> None:
        """If profile lacks education_level, degree rule with requirements should be UNKNOWN."""
        profile = _make_profile(education_level=None)
        opp = _make_opportunity(description="Open to Bachelor/Undergraduate students.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["degree"]["status"] == "UNKNOWN"


class TestGraduationYearRule:
    """Tests for graduation year / batch constraint rule."""

    def test_matching_batch_passes(self, engine: EligibilityEngine) -> None:
        """Profile year matching opportunity batch should PASS."""
        profile = _make_profile(graduation_year=2026)
        opp = _make_opportunity(description="Batch of 2025, 2026 graduates eligible.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["graduation_year"]["status"] == "PASS"

    def test_non_matching_batch_fails(self, engine: EligibilityEngine) -> None:
        """Profile year not in opportunity batch should FAIL."""
        profile = _make_profile(graduation_year=2024)
        opp = _make_opportunity(description="Only Batch of 2026 graduates are eligible.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["graduation_year"]["status"] == "FAIL"

    def test_no_year_constraint_is_unknown(self, engine: EligibilityEngine) -> None:
        """No year mentioned in opportunity text should be UNKNOWN."""
        profile = _make_profile(graduation_year=2026)
        opp = _make_opportunity(title="Open Hackathon", description="Open to all. No restrictions.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["graduation_year"]["status"] == "UNKNOWN"

    def test_missing_profile_year_is_unknown(self, engine: EligibilityEngine) -> None:
        """If profile lacks graduation_year but opportunity specifies batch, should be UNKNOWN."""
        profile = _make_profile(graduation_year=None)
        opp = _make_opportunity(description="Batch of 2026 graduates only.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["graduation_year"]["status"] == "UNKNOWN"


class TestBranchRule:
    """Tests for branch / major constraint rule."""

    def test_cs_branch_matches_cs_requirement(self, engine: EligibilityEngine) -> None:
        """CS student should pass CS-only requirement."""
        profile = _make_profile(branch="Computer Science")
        opp = _make_opportunity(description="Open to Computer Science majors only.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["branch"]["status"] == "PASS"

    def test_mech_branch_fails_cs_requirement(self, engine: EligibilityEngine) -> None:
        """Mechanical Engineering student should fail CS-only requirement."""
        profile = _make_profile(branch="Mechanical Engineering")
        opp = _make_opportunity(description="Open to Computer Science majors only.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["branch"]["status"] == "FAIL"

    def test_no_branch_restriction_is_unknown(self, engine: EligibilityEngine) -> None:
        """No branch restriction in opportunity should produce UNKNOWN."""
        profile = _make_profile(branch="Computer Science")
        opp = _make_opportunity(description="All students are welcome!")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["branch"]["status"] == "UNKNOWN"

    def test_missing_profile_branch_is_unknown(self, engine: EligibilityEngine) -> None:
        """If profile lacks branch but opportunity restricts branches, should be UNKNOWN."""
        profile = _make_profile(branch=None)
        opp = _make_opportunity(description="CS only majors accepted.")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["branch"]["status"] == "UNKNOWN"


class TestLocationRule:
    """Tests for location and participation mode constraint rule."""

    def test_remote_always_passes(self, engine: EligibilityEngine, profile: ProfileSchema) -> None:
        """Remote opportunity should always PASS location rule."""
        opp = _make_opportunity(mode=OpportunityMode.REMOTE, location="Global")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["location"]["status"] == "PASS"

    def test_onsite_matching_location_passes(self, engine: EligibilityEngine) -> None:
        """Onsite opportunity in preferred location should PASS."""
        profile = _make_profile(preferred_locations=["Bangalore", "Mumbai"])
        opp = _make_opportunity(mode=OpportunityMode.ONSITE, location="Bangalore, India")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["location"]["status"] == "PASS"

    def test_onsite_strict_nonmatch_fails(self, engine: EligibilityEngine) -> None:
        """Onsite opportunity with strict_location=True and no match should FAIL."""
        profile = _make_profile(
            preferred_locations=["Bangalore"],
            constraints={"strict_location": True},
        )
        opp = _make_opportunity(mode=OpportunityMode.ONSITE, location="San Francisco, CA")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["location"]["status"] == "FAIL"

    def test_no_profile_locations_is_unknown(self, engine: EligibilityEngine) -> None:
        """No preferred locations in profile with onsite opportunity should be UNKNOWN."""
        profile = _make_profile(preferred_locations=[])
        opp = _make_opportunity(mode=OpportunityMode.ONSITE, location="London, UK")
        result = engine.evaluate(profile, opp)
        assert result.rule_results["location"]["status"] == "UNKNOWN"


class TestTeamSizeRule:
    """Tests for team size constraint rule."""

    def test_no_team_size_is_unknown(self, engine: EligibilityEngine, profile: ProfileSchema) -> None:
        """No team size constraints should produce UNKNOWN."""
        opp = _make_opportunity(team_size_min=None, team_size_max=None)
        result = engine.evaluate(profile, opp)
        assert result.rule_results["team_size"]["status"] == "UNKNOWN"

    def test_solo_user_with_team_min_gt1_fails(self, engine: EligibilityEngine) -> None:
        """Solo-only user should fail when min team size > 1."""
        profile = _make_profile(constraints={"solo_only": True})
        opp = _make_opportunity(team_size_min=3, team_size_max=5)
        result = engine.evaluate(profile, opp)
        assert result.rule_results["team_size"]["status"] == "FAIL"

    def test_team_size_without_solo_constraint_passes(self, engine: EligibilityEngine, profile: ProfileSchema) -> None:
        """Team size range is fine when user has no solo_only constraint."""
        opp = _make_opportunity(team_size_min=2, team_size_max=4)
        result = engine.evaluate(profile, opp)
        assert result.rule_results["team_size"]["status"] == "PASS"


# ===========================================================================
# T-3.2: Tri-State Resolution Tests
# ===========================================================================

class TestTriStateResolution:
    """Tests for overall eligibility state resolution."""

    def test_all_pass_gives_eligible(self, engine: EligibilityEngine) -> None:
        """Profile matching all detectable criteria should be ELIGIBLE."""
        profile = _make_profile(
            education_level="B.Tech",
            graduation_year=2026,
            branch="Computer Science",
            preferred_locations=["Remote"],
        )
        opp = _make_opportunity(
            description="Open to Bachelor/B.Tech students, Batch of 2026. CS only majors.",
            mode=OpportunityMode.REMOTE,
            registration_deadline=datetime.now(UTC) + timedelta(days=30),
            team_size_min=1,
            team_size_max=5,
        )
        result = engine.evaluate(profile, opp)
        assert result.state == EligibilityState.ELIGIBLE
        assert result.confidence is not None
        assert result.confidence >= 0.9

    def test_one_fail_gives_ineligible(self, engine: EligibilityEngine) -> None:
        """A single rule failure should make overall state INELIGIBLE (hard exclusion dominance)."""
        profile = _make_profile(
            education_level="B.Tech",
            graduation_year=2024,
            branch="Computer Science",
        )
        opp = _make_opportunity(
            description="Only Batch of 2026 graduates. Open to Bachelor students.",
            registration_deadline=datetime.now(UTC) + timedelta(days=30),
            mode=OpportunityMode.REMOTE,
        )
        result = engine.evaluate(profile, opp)
        assert result.state == EligibilityState.INELIGIBLE

    def test_no_detectable_requirements_gives_unknown(self, engine: EligibilityEngine) -> None:
        """Opportunity with no detectable requirements should give UNKNOWN."""
        profile = _make_profile(preferred_locations=[])
        opp = _make_opportunity(
            title="Fun Weekend Event",
            description="Join us for fun!",
            registration_deadline=None,
            mode=None,
            location=None,
            team_size_min=None,
            team_size_max=None,
        )
        result = engine.evaluate(profile, opp)
        # All rules should be UNKNOWN -> overall UNKNOWN
        assert result.state == EligibilityState.UNKNOWN

    def test_evidence_dict_populated(self, engine: EligibilityEngine) -> None:
        """Evidence dict should be populated for rules that return evidence."""
        profile = _make_profile()
        opp = _make_opportunity(registration_deadline=datetime.now(UTC) + timedelta(days=10))
        result = engine.evaluate(profile, opp)
        # At least deadline should have evidence
        assert isinstance(result.evidence, dict)

    def test_rule_results_contain_all_rules(self, engine: EligibilityEngine, profile: ProfileSchema, opportunity: OpportunitySchema) -> None:
        """All 6 rules should appear in rule_results."""
        result = engine.evaluate(profile, opportunity)
        expected_rules = {"deadline", "degree", "graduation_year", "branch", "location", "team_size"}
        assert expected_rules == set(result.rule_results.keys())

    def test_each_rule_result_has_status_and_reason(self, engine: EligibilityEngine, profile: ProfileSchema, opportunity: OpportunitySchema) -> None:
        """Each rule result should have 'status' and 'reason' keys."""
        result = engine.evaluate(profile, opportunity)
        for rule_name, details in result.rule_results.items():
            assert "status" in details, f"Rule '{rule_name}' missing 'status'"
            assert "reason" in details, f"Rule '{rule_name}' missing 'reason'"
            assert details["status"] in {"PASS", "FAIL", "UNKNOWN"}


# ===========================================================================
# T-3.3: UNKNOWN Preservation Tests (AC-3.3)
# ===========================================================================

class TestUnknownPreservation:
    """UNKNOWN must never be inferred as ELIGIBLE or INELIGIBLE when evidence is missing."""

    def test_missing_education_preserves_unknown(self, engine: EligibilityEngine) -> None:
        """Missing profile education_level with degree requirement should be UNKNOWN overall."""
        profile = _make_profile(education_level=None)
        opp = _make_opportunity(
            description="Open to Bachelor/Undergraduate students.",
            registration_deadline=datetime.now(UTC) + timedelta(days=30),
            mode=OpportunityMode.REMOTE,
        )
        result = engine.evaluate(profile, opp)
        # Degree rule UNKNOWN with "missing profile" triggers overall UNKNOWN even with PASS deadline
        assert result.state == EligibilityState.UNKNOWN

    def test_missing_graduation_year_preserves_unknown(self, engine: EligibilityEngine) -> None:
        """Missing graduation_year with batch requirement preserves UNKNOWN."""
        profile = _make_profile(graduation_year=None, education_level="B.Tech")
        opp = _make_opportunity(
            description="Batch of 2026 graduates. Bachelor students welcome.",
            registration_deadline=datetime.now(UTC) + timedelta(days=30),
            mode=OpportunityMode.REMOTE,
        )
        result = engine.evaluate(profile, opp)
        assert result.state == EligibilityState.UNKNOWN

    def test_missing_branch_preserves_unknown(self, engine: EligibilityEngine) -> None:
        """Missing profile branch with CS requirement preserves UNKNOWN."""
        profile = _make_profile(branch=None, education_level="B.Tech")
        opp = _make_opportunity(
            description="Open to Bachelor students. CS only majors.",
            registration_deadline=datetime.now(UTC) + timedelta(days=30),
            mode=OpportunityMode.REMOTE,
        )
        result = engine.evaluate(profile, opp)
        assert result.state == EligibilityState.UNKNOWN

    def test_hard_failure_overrides_unknown(self, engine: EligibilityEngine) -> None:
        """Even with UNKNOWN rules, a hard failure should produce INELIGIBLE, not UNKNOWN."""
        profile = _make_profile(education_level=None, graduation_year=None)
        opp = _make_opportunity(
            description="Bachelor students. CS only majors.",
            registration_deadline=datetime.now(UTC) - timedelta(days=5),  # EXPIRED
            mode=OpportunityMode.REMOTE,
        )
        result = engine.evaluate(profile, opp)
        # Hard failure (expired deadline) should override UNKNOWNs
        assert result.state == EligibilityState.INELIGIBLE

    def test_confidence_lower_for_unknown(self, engine: EligibilityEngine) -> None:
        """UNKNOWN states should have lower confidence than ELIGIBLE or INELIGIBLE."""
        profile = _make_profile(education_level=None)
        opp = _make_opportunity(
            description="Bachelor students welcome.",
            registration_deadline=datetime.now(UTC) + timedelta(days=30),
            mode=OpportunityMode.REMOTE,
        )
        result = engine.evaluate(profile, opp)
        assert result.state == EligibilityState.UNKNOWN
        assert result.confidence is not None
        assert result.confidence < 0.9  # Should be lower than ELIGIBLE confidence
