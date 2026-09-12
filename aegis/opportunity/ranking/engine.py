"""
Aegis — Hybrid Ranking Engine

Combines hard eligibility, structured feature overlap, and semantic similarity into
a transparent, auditable match score (AC-3.5, AC-3.6).
Enforces hard exclusion dominance: any INELIGIBLE opportunity is clamped to 0.0 (AC-3.4).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.schemas.domain import (
    EligibilityDecisionSchema,
    EligibilityState,
    MatchScoreSchema,
    OpportunitySchema,
    ProfileSchema,
)
from opportunity.eligibility.engine import EligibilityEngine
from opportunity.matching.explainer import MatchExplainer
from opportunity.matching.overlap import calculate_feature_overlap
from opportunity.matching.semantic import SemanticMatcher

# Default weights (configurable)
DEFAULT_WEIGHT_ELIGIBILITY = 0.35
DEFAULT_WEIGHT_FEATURES = 0.35
DEFAULT_WEIGHT_SEMANTIC = 0.30


class RankingEngine:
    """Hybrid opportunity matching and ranking engine."""

    def __init__(
        self,
        weight_eligibility: float = DEFAULT_WEIGHT_ELIGIBILITY,
        weight_features: float = DEFAULT_WEIGHT_FEATURES,
        weight_semantic: float = DEFAULT_WEIGHT_SEMANTIC,
        eligibility_engine: EligibilityEngine | None = None,
        semantic_matcher: SemanticMatcher | None = None,
        explainer: MatchExplainer | None = None,
    ) -> None:
        # Normalize weights to sum to 1.0
        total = weight_eligibility + weight_features + weight_semantic
        self.w_eligibility = weight_eligibility / total
        self.w_features = weight_features / total
        self.w_semantic = weight_semantic / total

        self.eligibility_engine = eligibility_engine or EligibilityEngine()
        self.semantic_matcher = semantic_matcher or SemanticMatcher()
        self.explainer = explainer or MatchExplainer()

    def score_pair(
        self,
        profile: ProfileSchema,
        opportunity: OpportunitySchema,
        eligibility: EligibilityDecisionSchema | None = None,
        now: datetime | None = None,
    ) -> tuple[MatchScoreSchema, EligibilityDecisionSchema]:
        """
        Evaluate and compute the hybrid score for a single (profile, opportunity) pair.
        Returns (MatchScoreSchema, EligibilityDecisionSchema).
        """
        eval_time = now or datetime.now(UTC)

        # 1. Evaluate eligibility if not provided
        if eligibility is None:
            eligibility = self.eligibility_engine.evaluate(profile, opportunity, current_time=eval_time)

        # 2. Convert eligibility state to numeric score
        if eligibility.state == EligibilityState.ELIGIBLE:
            eligibility_num = 1.0
        elif eligibility.state == EligibilityState.UNKNOWN:
            eligibility_num = 0.5  # Neutral for unconfirmed criteria
        else:  # INELIGIBLE
            eligibility_num = 0.0

        # 3. Structured feature overlap
        feature_score, feature_details = calculate_feature_overlap(profile, opportunity)

        # 4. Semantic similarity
        semantic_score = self.semantic_matcher.compute_similarity(profile, opportunity)

        # 5. Composite Hybrid Score
        raw_composite = (
            self.w_eligibility * eligibility_num +
            self.w_features * feature_score +
            self.w_semantic * semantic_score
        )

        # Hard Exclusion Dominance (AC-3.4, §2.4):
        # Hard disqualifications always override high similarity scores
        if eligibility.state == EligibilityState.INELIGIBLE:
            final_score = 0.0
        else:
            final_score = max(0.0, min(1.0, round(raw_composite, 4)))

        # 6. Weights record
        weights_used = {
            "w_eligibility": round(self.w_eligibility, 4),
            "w_features": round(self.w_features, 4),
            "w_semantic": round(self.w_semantic, 4),
        }

        # 7. Audit breakdown
        score_breakdown: dict[str, Any] = {
            "eligibility": {
                "state": eligibility.state.value,
                "score": eligibility_num,
                "weight": weights_used["w_eligibility"],
                "rule_results": eligibility.rule_results,
            },
            "feature_overlap": feature_details,
            "semantic_similarity": {
                "score": semantic_score,
                "weight": weights_used["w_semantic"],
            },
            "raw_composite": round(raw_composite, 4),
            "final_score": final_score,
            "disqualified": eligibility.state == EligibilityState.INELIGIBLE,
        }

        # 8. Fact-grounded explanation
        explanation = self.explainer.generate_explanation(
            profile=profile,
            opportunity=opportunity,
            eligibility=eligibility,
            feature_breakdown=feature_details,
            semantic_score=semantic_score,
        )

        match_score = MatchScoreSchema(
            id=uuid.uuid4(),
            opportunity_id=opportunity.id,
            profile_id=profile.id,
            final_score=final_score,
            eligibility_score=eligibility_num,
            feature_overlap_score=feature_score,
            semantic_similarity_score=semantic_score,
            weights_used=weights_used,
            score_breakdown=score_breakdown,
            explanation=explanation,
            user_feedback=None,
            scored_at=eval_time,
        )

        return match_score, eligibility

    def rank_opportunities(
        self,
        profile: ProfileSchema,
        opportunities: list[OpportunitySchema],
        now: datetime | None = None,
    ) -> list[tuple[OpportunitySchema, MatchScoreSchema, EligibilityDecisionSchema]]:
        """
        Score and rank a collection of opportunities for a profile.
        Returns list of (opportunity, match_score, eligibility) sorted by final_score descending.
        """
        results: list[tuple[OpportunitySchema, MatchScoreSchema, EligibilityDecisionSchema]] = []
        for opp in opportunities:
            score, elig = self.score_pair(profile, opp, now=now)
            results.append((opp, score, elig))

        # Sort: highest final_score first, then by earliest registration deadline
        results.sort(
            key=lambda item: (
                item[1].final_score,
                -item[0].registration_deadline.timestamp() if item[0].registration_deadline else float("-inf"),
            ),
            reverse=True,
        )
        return results
