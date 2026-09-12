"""
Aegis — Feed API Router

Provides endpoints for personalized ranked opportunities feed, evaluation triggers,
and user feedback actions.
"""

from __future__ import annotations

import uuid
from typing import Any

from core.schemas.domain import UserFeedback
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from storage.database import get_db_session
from storage.repositories.eligibility_repository import EligibilityRepository
from storage.repositories.match_repository import MatchRepository
from storage.repositories.opportunity_repository import OpportunityRepository
from storage.repositories.profile_repository import ProfileRepository

router = APIRouter(prefix="/api/v1/feed", tags=["feed"])


class FeedbackRequest(BaseModel):
    """Payload to record user interaction with an opportunity."""

    opportunity_id: uuid.UUID
    feedback: UserFeedback


class FeedItemResponse(BaseModel):
    """An opportunity in the user's ranked feed."""

    opportunity_id: uuid.UUID
    title: str
    category: str
    organizer: str | None = None
    url: str
    description: str | None = None
    location: str | None = None
    mode: str | None = None
    registration_deadline: str | None = None
    final_score: float
    eligibility_state: str
    explanation: str
    score_breakdown: dict[str, Any]
    user_feedback: str | None = None


@router.get("/{user_id}", response_model=list[FeedItemResponse])
async def get_user_feed(
    user_id: uuid.UUID,
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    exclude_dismissed: bool = Query(True),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
) -> list[FeedItemResponse]:
    """
    Retrieve ranked opportunities feed for a user profile.
    If match scores don't exist yet, automatically computes and persists them.
    """
    profile = await ProfileRepository.get_by_user_id(db, user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile for user {user_id} not found.",
        )

    match_repo = MatchRepository(db)
    elig_repo = EligibilityRepository(db)

    # Fetch existing ranked matches
    matches = await match_repo.get_ranked_matches(
        profile_id=profile.id,
        min_score=min_score,
        exclude_dismissed=exclude_dismissed,
        limit=limit,
    )

    # If no matches found, run on-demand evaluation of stored opportunities
    if not matches:
        opportunities = await OpportunityRepository.list_opportunities(db, limit=100)
        if opportunities:
            from core.schemas.domain import OpportunitySchema, ProfileSchema
            from opportunity.ranking.engine import RankingEngine

            p_schema = ProfileSchema.model_validate(profile)
            opp_schemas = [OpportunitySchema.model_validate(o) for o in opportunities]

            engine = RankingEngine()
            ranked_results = engine.rank_opportunities(p_schema, opp_schemas)

            for opp_schema, score_schema, elig_schema in ranked_results:
                await elig_repo.save_decision(
                    opportunity_id=opp_schema.id,
                    profile_id=p_schema.id,
                    state=elig_schema.state,
                    evidence=elig_schema.evidence,
                    rule_results=elig_schema.rule_results,
                    confidence=elig_schema.confidence,
                )
                await match_repo.save_match_score(
                    opportunity_id=opp_schema.id,
                    profile_id=p_schema.id,
                    final_score=score_schema.final_score,
                    eligibility_score=score_schema.eligibility_score,
                    feature_overlap_score=score_schema.feature_overlap_score,
                    semantic_similarity_score=score_schema.semantic_similarity_score,
                    weights_used=score_schema.weights_used,
                    score_breakdown=score_schema.score_breakdown,
                    explanation=score_schema.explanation,
                )
            await db.commit()

            matches = await match_repo.get_ranked_matches(
                profile_id=profile.id,
                min_score=min_score,
                exclude_dismissed=exclude_dismissed,
                limit=limit,
            )

    from opportunity.filters import is_hackathon_visible

    feed_items: list[FeedItemResponse] = []
    for m in matches:
        opp = await OpportunityRepository.get_by_id(db, m.opportunity_id)
        if not opp:
            continue

        if not is_hackathon_visible(opp):
            continue

        elig = await elig_repo.get_by_pair(m.opportunity_id, profile.id)
        elig_state = elig.state if elig else "UNKNOWN"

        deadline_str = (
            opp.registration_deadline.isoformat()
            if opp.registration_deadline
            else None
        )

        feed_items.append(
            FeedItemResponse(
                opportunity_id=opp.id,
                title=opp.title,
                category=opp.category,
                organizer=opp.organizer,
                url=opp.url,
                description=opp.description,
                location=opp.location,
                mode=opp.mode,
                registration_deadline=deadline_str,
                final_score=m.final_score,
                eligibility_state=elig_state,
                explanation=m.explanation,
                score_breakdown=m.score_breakdown,
                user_feedback=m.user_feedback,
            )
        )

    return feed_items


@router.post("/{user_id}/evaluate", status_code=status.HTTP_200_OK)
async def evaluate_opportunities_for_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Trigger re-evaluation and hybrid scoring of all opportunities for a user profile.
    """
    profile = await ProfileRepository.get_by_user_id(db, user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile for user {user_id} not found.",
        )

    opportunities = await OpportunityRepository.list_opportunities(db, limit=500)
    if not opportunities:
        return {"evaluated_count": 0, "message": "No opportunities found to evaluate."}

    from core.schemas.domain import OpportunitySchema, ProfileSchema
    from opportunity.ranking.engine import RankingEngine

    p_schema = ProfileSchema.model_validate(profile)
    opp_schemas = [OpportunitySchema.model_validate(o) for o in opportunities]

    engine = RankingEngine()
    ranked_results = engine.rank_opportunities(p_schema, opp_schemas)

    elig_repo = EligibilityRepository(db)
    match_repo = MatchRepository(db)

    for opp_schema, score_schema, elig_schema in ranked_results:
        await elig_repo.save_decision(
            opportunity_id=opp_schema.id,
            profile_id=p_schema.id,
            state=elig_schema.state,
            evidence=elig_schema.evidence,
            rule_results=elig_schema.rule_results,
            confidence=elig_schema.confidence,
        )
        await match_repo.save_match_score(
            opportunity_id=opp_schema.id,
            profile_id=p_schema.id,
            final_score=score_schema.final_score,
            eligibility_score=score_schema.eligibility_score,
            feature_overlap_score=score_schema.feature_overlap_score,
            semantic_similarity_score=score_schema.semantic_similarity_score,
            weights_used=score_schema.weights_used,
            score_breakdown=score_schema.score_breakdown,
            explanation=score_schema.explanation,
        )
    await db.commit()

    return {
        "evaluated_count": len(ranked_results),
        "message": f"Successfully evaluated {len(ranked_results)} opportunities.",
    }


@router.post("/{user_id}/feedback", status_code=status.HTTP_200_OK)
async def submit_user_feedback(
    user_id: uuid.UUID,
    payload: FeedbackRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """
    Record user feedback action (interested, dismissed, applied, not_eligible) on an opportunity.
    """
    profile = await ProfileRepository.get_by_user_id(db, user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile for user {user_id} not found.",
        )

    match_repo = MatchRepository(db)
    updated = await match_repo.update_feedback(
        opportunity_id=payload.opportunity_id,
        profile_id=profile.id,
        feedback=payload.feedback,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match score not found for this opportunity and user.",
        )

    await db.commit()
    return {
        "status": "success",
        "opportunity_id": str(payload.opportunity_id),
        "user_feedback": payload.feedback.value,
    }
