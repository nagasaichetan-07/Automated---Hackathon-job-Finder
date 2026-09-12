"""
Aegis — Matching, Ranking & Explainability Test Suite (Phase 5)

Tests: T-3.4, T-3.5, T-3.6, T-3.7
- Skill overlap, location overlap, category overlap calculations
- Semantic similarity (deterministic vectorizer fallback)
- Hybrid score calculation with configurable weights
- Hard disqualification score clamping (INELIGIBLE => final_score = 0.0)
- Fact-grounded explanations with no hallucinations
- Ranking order: highest score first
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from core.schemas.domain import (
    EligibilityDecisionSchema,
    EligibilityState,
    OpportunityCategory,
    OpportunityMode,
    OpportunitySchema,
    ProfileSchema,
)
from opportunity.matching.explainer import MatchExplainer
from opportunity.matching.overlap import (
    calculate_category_overlap,
    calculate_feature_overlap,
    calculate_location_overlap,
    calculate_skill_overlap,
)
from opportunity.matching.semantic import (
    SemanticMatcher,
    _cosine_similarity,
    _tokenize_and_vectorize,
)
from opportunity.ranking.engine import RankingEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(**overrides: Any) -> ProfileSchema:
    base: dict[str, Any] = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        education_level="B.Tech",
        graduation_year=2026,
        branch="Computer Science",
        skills=["Python", "React", "SQL", "FastAPI"],
        preferred_locations=["Remote", "Bangalore"],
        opportunity_types=[OpportunityCategory.HACKATHON, OpportunityCategory.INTERNSHIP],
        interests=["AI", "Web Development", "Machine Learning"],
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
    base: dict[str, Any] = dict(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        external_id="test-opp-001",
        title="AI Hackathon 2026",
        category=OpportunityCategory.HACKATHON,
        organizer="Test Org",
        url="https://example.com/hackathon",
        description="Build autonomous AI agents using Python and React.",
        registration_deadline=datetime.now(UTC) + timedelta(days=30),
        start_date=None,
        end_date=None,
        location=None,
        mode=OpportunityMode.REMOTE,
        eligibility_text=None,
        team_size_min=None,
        team_size_max=None,
        prize=None,
        skills_themes=["Python", "React", "FastAPI"],
        evidence={},
        content_hash=None,
        published_at=None,
        collected_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    base.update(overrides)
    return OpportunitySchema.model_validate(base)


def _make_eligibility(state: EligibilityState, **overrides: Any) -> EligibilityDecisionSchema:
    base: dict[str, Any] = dict(
        id=uuid.uuid4(),
        opportunity_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        state=state,
        evidence={},
        rule_results={
            "deadline": {"status": "PASS", "reason": "Active deadline.", "confidence": 1.0},
        },
        confidence=1.0 if state == EligibilityState.INELIGIBLE else 0.95,
        evaluated_at=datetime.now(UTC),
    )
    base.update(overrides)
    return EligibilityDecisionSchema.model_validate(base)


# ===========================================================================
# T-3.4: Structured Feature Overlap Tests
# ===========================================================================

class TestSkillOverlap:
    """Tests for skill alignment calculation."""

    def test_perfect_skill_match(self) -> None:
        """All opportunity skills present in profile should score 1.0."""
        score, matched, missing = calculate_skill_overlap(
            profile_skills=["Python", "React", "SQL"],
            opportunity_skills=["Python", "React", "SQL"],
        )
        assert score == 1.0
        assert len(matched) == 3
        assert len(missing) == 0

    def test_partial_skill_match(self) -> None:
        """Partial match should produce intermediate score."""
        score, matched, missing = calculate_skill_overlap(
            profile_skills=["Python", "React"],
            opportunity_skills=["Python", "React", "Go", "Kubernetes"],
        )
        assert 0.0 < score < 1.0
        assert "python" in matched
        assert "react" in matched
        assert "go" in missing or "kubernetes" in missing

    def test_no_skill_match(self) -> None:
        """Zero overlap should produce 0.0 score."""
        score, matched, missing = calculate_skill_overlap(
            profile_skills=["Java", "C++"],
            opportunity_skills=["Python", "React"],
        )
        assert score == 0.0
        assert len(matched) == 0

    def test_empty_profile_skills(self) -> None:
        """Empty profile skills should return 0.0."""
        score, matched, missing = calculate_skill_overlap(
            profile_skills=[],
            opportunity_skills=["Python", "React"],
        )
        assert score == 0.0

    def test_text_search_fallback_when_no_opp_skills(self) -> None:
        """Should search opportunity text when no explicit skill tags exist."""
        score, matched, _ = calculate_skill_overlap(
            profile_skills=["python", "react", "sql"],
            opportunity_skills=[],
            opportunity_text="Build a web app using Python and React framework.",
        )
        assert score > 0.0
        assert "python" in matched
        assert "react" in matched

    def test_case_insensitive_matching(self) -> None:
        """Skill matching should be case-insensitive."""
        score, matched, missing = calculate_skill_overlap(
            profile_skills=["PYTHON", "react"],
            opportunity_skills=["python", "React"],
        )
        assert score == 1.0


class TestLocationOverlap:
    """Tests for location/mode alignment scoring."""

    def test_remote_always_1(self) -> None:
        """Remote mode should always return 1.0."""
        score = calculate_location_overlap(
            preferred_locations=["Bangalore"],
            opportunity_location="San Francisco",
            mode=OpportunityMode.REMOTE,
        )
        assert score == 1.0

    def test_onsite_matching_location(self) -> None:
        """Matching onsite location should return 1.0."""
        score = calculate_location_overlap(
            preferred_locations=["Bangalore", "Mumbai"],
            opportunity_location="Bangalore, India",
            mode=OpportunityMode.ONSITE,
        )
        assert score == 1.0

    def test_onsite_non_matching_location(self) -> None:
        """Non-matching onsite should return low score."""
        score = calculate_location_overlap(
            preferred_locations=["Bangalore"],
            opportunity_location="New York, USA",
            mode=OpportunityMode.ONSITE,
        )
        assert score < 0.5

    def test_no_preference_neutral(self) -> None:
        """No user preferences should return neutral 0.5."""
        score = calculate_location_overlap(
            preferred_locations=[],
            opportunity_location="London",
            mode=OpportunityMode.ONSITE,
        )
        assert score == 0.5

    def test_unspecified_location_neutral(self) -> None:
        """Unspecified opportunity location should return neutral 0.5."""
        score = calculate_location_overlap(
            preferred_locations=["Bangalore"],
            opportunity_location=None,
            mode=OpportunityMode.ONSITE,
        )
        assert score == 0.5


class TestCategoryOverlap:
    """Tests for opportunity type alignment."""

    def test_matching_category(self) -> None:
        assert calculate_category_overlap(
            [OpportunityCategory.HACKATHON, OpportunityCategory.INTERNSHIP],
            OpportunityCategory.HACKATHON,
        ) == 1.0

    def test_non_matching_category(self) -> None:
        score = calculate_category_overlap(
            [OpportunityCategory.HACKATHON],
            OpportunityCategory.JOB,
        )
        assert score < 0.5

    def test_no_preference_high_neutral(self) -> None:
        """No preferred types should still return high neutral score."""
        score = calculate_category_overlap([], OpportunityCategory.HACKATHON)
        assert score >= 0.7


class TestCompositeFeatureOverlap:
    """Tests for composite feature overlap score."""

    def test_composite_between_0_and_1(self) -> None:
        """Composite score should be clamped [0, 1]."""
        profile = _make_profile()
        opp = _make_opportunity()
        score, details = calculate_feature_overlap(profile, opp)
        assert 0.0 <= score <= 1.0

    def test_details_contain_all_components(self) -> None:
        """Details dict should have skill_overlap, location_compatibility, category_alignment."""
        profile = _make_profile()
        opp = _make_opportunity()
        _, details = calculate_feature_overlap(profile, opp)
        assert "skill_overlap" in details
        assert "location_compatibility" in details
        assert "category_alignment" in details
        assert "composite" in details

    def test_high_overlap_for_well_matched_pair(self) -> None:
        """Well-matched profile-opportunity pair should produce high composite."""
        profile = _make_profile(
            skills=["Python", "React", "FastAPI"],
            preferred_locations=["Remote"],
            opportunity_types=[OpportunityCategory.HACKATHON],
        )
        opp = _make_opportunity(
            skills_themes=["Python", "React", "FastAPI"],
            mode=OpportunityMode.REMOTE,
            category=OpportunityCategory.HACKATHON,
        )
        score, _ = calculate_feature_overlap(profile, opp)
        assert score >= 0.8


# ===========================================================================
# T-3.5: Semantic Similarity Tests (Deterministic Vectorizer)
# ===========================================================================

class TestSemanticMatcher:
    """Tests for deterministic vectorizer fallback semantic matching."""

    def test_identical_text_max_similarity(self) -> None:
        """Identical text should produce high similarity."""
        vec1 = _tokenize_and_vectorize("python react fastapi machine learning")
        vec2 = _tokenize_and_vectorize("python react fastapi machine learning")
        sim = _cosine_similarity(vec1, vec2)
        assert sim >= 0.99

    def test_disjoint_text_low_similarity(self) -> None:
        """Completely different text should produce low similarity."""
        vec1 = _tokenize_and_vectorize("quantum physics theoretical mechanics")
        vec2 = _tokenize_and_vectorize("cooking recipes desserts baking")
        sim = _cosine_similarity(vec1, vec2)
        assert sim < 0.1

    def test_empty_text_zero_similarity(self) -> None:
        """Empty text should produce zero similarity."""
        assert _cosine_similarity({}, {}) == 0.0
        assert _cosine_similarity(_tokenize_and_vectorize("python"), {}) == 0.0

    def test_compute_similarity_returns_bounded_value(self) -> None:
        """SemanticMatcher.compute_similarity should return a float in [0, 1]."""
        matcher = SemanticMatcher()
        profile = _make_profile()
        opp = _make_opportunity()
        score = matcher.compute_similarity(profile, opp)
        assert 0.0 <= score <= 1.0

    def test_profile_text_contains_skills(self) -> None:
        """Profile text should include skills and interests."""
        matcher = SemanticMatcher()
        profile = _make_profile(skills=["Python", "React"], interests=["AI"])
        text = matcher.build_profile_text(profile)
        assert "Python" in text
        assert "React" in text
        assert "AI" in text

    def test_opportunity_text_contains_title_and_description(self) -> None:
        """Opportunity text should include title and description."""
        matcher = SemanticMatcher()
        opp = _make_opportunity(title="AI Hackathon", description="Build autonomous agents.")
        text = matcher.build_opportunity_text(opp)
        assert "AI Hackathon" in text
        assert "autonomous agents" in text


# ===========================================================================
# T-3.6: Hybrid Ranking Engine Tests
# ===========================================================================

class TestRankingEngine:
    """Tests for the hybrid ranking engine with score composition and clamping."""

    def test_score_pair_returns_match_and_eligibility(self) -> None:
        """score_pair should return a MatchScoreSchema and EligibilityDecisionSchema."""
        engine = RankingEngine()
        profile = _make_profile()
        opp = _make_opportunity()
        match_score, elig = engine.score_pair(profile, opp)
        assert 0.0 <= match_score.final_score <= 1.0
        assert elig.state in {EligibilityState.ELIGIBLE, EligibilityState.INELIGIBLE, EligibilityState.UNKNOWN}

    def test_ineligible_clamped_to_zero(self) -> None:
        """INELIGIBLE opportunity must have final_score = 0.0 (AC-3.4 hard exclusion dominance)."""
        engine = RankingEngine()
        profile = _make_profile()
        opp = _make_opportunity(
            registration_deadline=datetime.now(UTC) - timedelta(days=5),  # expired
        )
        match_score, elig = engine.score_pair(profile, opp)
        assert elig.state == EligibilityState.INELIGIBLE
        assert match_score.final_score == 0.0

    def test_score_breakdown_has_all_components(self) -> None:
        """Score breakdown should contain eligibility, feature_overlap, semantic_similarity."""
        engine = RankingEngine()
        profile = _make_profile()
        opp = _make_opportunity()
        match_score, _ = engine.score_pair(profile, opp)
        breakdown = match_score.score_breakdown
        assert "eligibility" in breakdown
        assert "feature_overlap" in breakdown
        assert "semantic_similarity" in breakdown
        assert "disqualified" in breakdown

    def test_weights_sum_to_one(self) -> None:
        """Weights used should always sum to approximately 1.0."""
        engine = RankingEngine()
        profile = _make_profile()
        opp = _make_opportunity()
        match_score, _ = engine.score_pair(profile, opp)
        weights = match_score.weights_used
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01

    def test_custom_weights_respected(self) -> None:
        """Custom weights should be normalized and used."""
        engine = RankingEngine(
            weight_eligibility=0.5,
            weight_features=0.3,
            weight_semantic=0.2,
        )
        profile = _make_profile()
        opp = _make_opportunity()
        match_score, _ = engine.score_pair(profile, opp)
        assert match_score.weights_used["w_eligibility"] == 0.5
        assert match_score.weights_used["w_features"] == 0.3
        assert match_score.weights_used["w_semantic"] == 0.2

    def test_explanation_is_populated(self) -> None:
        """Explanation should be a non-empty string."""
        engine = RankingEngine()
        profile = _make_profile()
        opp = _make_opportunity()
        match_score, _ = engine.score_pair(profile, opp)
        assert isinstance(match_score.explanation, str)
        assert len(match_score.explanation) > 10

    def test_rank_opportunities_sorted_descending(self) -> None:
        """rank_opportunities should return results sorted by final_score descending."""
        engine = RankingEngine()
        profile = _make_profile()
        opps = [
            _make_opportunity(
                title="Good Match",
                skills_themes=["Python", "React", "FastAPI"],
                mode=OpportunityMode.REMOTE,
            ),
            _make_opportunity(
                title="Poor Match",
                skills_themes=["Rust", "Haskell", "Erlang"],
                mode=OpportunityMode.ONSITE,
                location="Tokyo, Japan",
            ),
            _make_opportunity(
                title="Expired",
                registration_deadline=datetime.now(UTC) - timedelta(days=5),
            ),
        ]
        results = engine.rank_opportunities(profile, opps)
        scores = [r[1].final_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_ineligible_ranked_last(self) -> None:
        """INELIGIBLE (score=0.0) opportunities should appear at the bottom of rankings."""
        engine = RankingEngine()
        profile = _make_profile()
        opps = [
            _make_opportunity(
                title="Expired Hackathon",
                registration_deadline=datetime.now(UTC) - timedelta(days=5),
            ),
            _make_opportunity(
                title="Good Match",
                skills_themes=["Python", "React"],
                mode=OpportunityMode.REMOTE,
            ),
        ]
        results = engine.rank_opportunities(profile, opps)
        # Last entry should be the expired one with score 0.0
        assert results[-1][1].final_score == 0.0
        assert results[0][1].final_score > 0.0

    def test_disqualified_flag_set_correctly(self) -> None:
        """Disqualified flag in score_breakdown should match INELIGIBLE state."""
        engine = RankingEngine()
        profile = _make_profile()

        # INELIGIBLE opportunity
        opp_expired = _make_opportunity(registration_deadline=datetime.now(UTC) - timedelta(days=5))
        score_expired, _ = engine.score_pair(profile, opp_expired)
        assert score_expired.score_breakdown["disqualified"] is True

        # ELIGIBLE opportunity
        opp_active = _make_opportunity(
            mode=OpportunityMode.REMOTE,
            registration_deadline=datetime.now(UTC) + timedelta(days=30),
        )
        score_active, _ = engine.score_pair(profile, opp_active)
        assert score_active.score_breakdown["disqualified"] is False


# ===========================================================================
# T-3.7: Fact-Grounded Explanation Tests
# ===========================================================================

class TestMatchExplainer:
    """Tests ensuring explanations trace to stored facts and never hallucinate."""

    @pytest.fixture
    def explainer(self) -> MatchExplainer:
        return MatchExplainer()

    def test_eligible_explanation_cites_rule_reasons(self, explainer: MatchExplainer) -> None:
        """ELIGIBLE explanation should cite at least one rule pass reason."""
        profile = _make_profile()
        opp = _make_opportunity()
        elig = _make_eligibility(
            EligibilityState.ELIGIBLE,
            rule_results={
                "deadline": {"status": "PASS", "reason": "Registration is active until 2026-10-01."},
                "degree": {"status": "PASS", "reason": "B.Tech satisfies bachelor requirement."},
            },
        )
        feature_breakdown = {
            "skill_overlap": {"matched_skills": ["python", "react"], "score": 0.8},
            "location_compatibility": {"mode": "remote", "score": 1.0},
        }
        explanation = explainer.generate_explanation(profile, opp, elig, feature_breakdown, 0.85)
        assert "Eligible" in explanation
        assert "Registration is active" in explanation or "B.Tech" in explanation

    def test_ineligible_explanation_cites_failure(self, explainer: MatchExplainer) -> None:
        """INELIGIBLE explanation should cite the failure reason."""
        profile = _make_profile()
        opp = _make_opportunity()
        elig = _make_eligibility(
            EligibilityState.INELIGIBLE,
            rule_results={
                "deadline": {"status": "FAIL", "reason": "Registration deadline expired on 2026-01-01."},
            },
        )
        explanation = explainer.generate_explanation(profile, opp, elig, {}, 0.0)
        assert "Ineligible" in explanation
        assert "expired" in explanation.lower() or "deadline" in explanation.lower()

    def test_unknown_explanation_mentions_pending(self, explainer: MatchExplainer) -> None:
        """UNKNOWN explanation should mention pending confirmation."""
        profile = _make_profile()
        opp = _make_opportunity()
        elig = _make_eligibility(
            EligibilityState.UNKNOWN,
            rule_results={
                "branch": {"status": "UNKNOWN", "reason": "Missing profile branch."},
            },
        )
        explanation = explainer.generate_explanation(profile, opp, elig, {}, 0.5)
        assert "pending" in explanation.lower() or "unconfirmed" in explanation.lower()

    def test_explanation_mentions_matched_skills(self, explainer: MatchExplainer) -> None:
        """Explanation should mention matched skills from feature breakdown."""
        profile = _make_profile()
        opp = _make_opportunity()
        elig = _make_eligibility(EligibilityState.ELIGIBLE)
        feature_breakdown = {
            "skill_overlap": {"matched_skills": ["python", "fastapi"], "score": 0.9},
            "location_compatibility": {"mode": "remote", "score": 1.0},
        }
        explanation = explainer.generate_explanation(profile, opp, elig, feature_breakdown, 0.9)
        assert "python" in explanation.lower() or "fastapi" in explanation.lower()

    def test_explanation_mentions_remote_mode(self, explainer: MatchExplainer) -> None:
        """Explanation should mention remote participation when mode is remote."""
        profile = _make_profile()
        opp = _make_opportunity(mode=OpportunityMode.REMOTE)
        elig = _make_eligibility(EligibilityState.ELIGIBLE)
        feature_breakdown = {
            "skill_overlap": {"matched_skills": [], "score": 0.0},
            "location_compatibility": {"mode": "remote", "score": 1.0},
        }
        explanation = explainer.generate_explanation(profile, opp, elig, feature_breakdown, 0.3)
        assert "remote" in explanation.lower()

    def test_explanation_mentions_deadline_when_active(self, explainer: MatchExplainer) -> None:
        """Explanation should mention deadline when opportunity has one."""
        profile = _make_profile()
        deadline = datetime.now(UTC) + timedelta(days=30)
        opp = _make_opportunity(registration_deadline=deadline)
        elig = _make_eligibility(EligibilityState.ELIGIBLE)
        feature_breakdown = {
            "skill_overlap": {"matched_skills": [], "score": 0.0},
            "location_compatibility": {"mode": "remote", "score": 1.0},
        }
        explanation = explainer.generate_explanation(profile, opp, elig, feature_breakdown, 0.3)
        assert "deadline" in explanation.lower() or "registration" in explanation.lower()

    def test_explanation_no_hallucinated_skills(self, explainer: MatchExplainer) -> None:
        """Explanation should NEVER mention skills not in the profile or breakdown."""
        profile = _make_profile(skills=["Python"])
        opp = _make_opportunity(skills_themes=["Python"])
        elig = _make_eligibility(EligibilityState.ELIGIBLE)
        feature_breakdown = {
            "skill_overlap": {"matched_skills": ["python"], "score": 1.0},
            "location_compatibility": {"mode": "remote", "score": 1.0},
        }
        explanation = explainer.generate_explanation(profile, opp, elig, feature_breakdown, 0.5)
        # Should not mention skills not in the matched list
        assert "java" not in explanation.lower()
        assert "kubernetes" not in explanation.lower()
        assert "go" not in explanation.lower()

    def test_ineligible_returns_early_without_extra_details(self, explainer: MatchExplainer) -> None:
        """INELIGIBLE explanation should return immediately with just the failure reason."""
        profile = _make_profile()
        opp = _make_opportunity()
        elig = _make_eligibility(
            EligibilityState.INELIGIBLE,
            rule_results={
                "degree": {"status": "FAIL", "reason": "Requires PhD, profile is B.Tech."},
            },
        )
        feature_breakdown = {
            "skill_overlap": {"matched_skills": ["python", "react"], "score": 0.9},
        }
        explanation = explainer.generate_explanation(profile, opp, elig, feature_breakdown, 0.95)
        # Should NOT mention matched skills because it returned early
        assert "Ineligible" in explanation
        assert "python" not in explanation.lower()
