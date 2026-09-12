"""
Aegis — Match Repository

Provides database access, upsert semantics, ranked queries, and feedback updates
for MatchScore entities.
"""

from __future__ import annotations

import uuid
from typing import Any

from core.schemas.domain import UserFeedback
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from storage.models.match_score import MatchScore


class MatchRepository:
    """Repository managing MatchScore persistence and queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, score_id: uuid.UUID) -> MatchScore | None:
        """Fetch match score by primary key ID."""
        stmt = select(MatchScore).where(MatchScore.id == score_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_pair(
        self,
        opportunity_id: uuid.UUID,
        profile_id: uuid.UUID,
    ) -> MatchScore | None:
        """Fetch score for a specific opportunity-profile pair."""
        stmt = select(MatchScore).where(
            MatchScore.opportunity_id == opportunity_id,
            MatchScore.profile_id == profile_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_ranked_matches(
        self,
        profile_id: uuid.UUID,
        min_score: float = 0.0,
        exclude_dismissed: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MatchScore]:
        """
        Fetch ranked matches for a profile ordered by final_score descending.
        Optionally filters out dismissed matches and low-scoring matches.
        """
        stmt = select(MatchScore).where(
            MatchScore.profile_id == profile_id,
            MatchScore.final_score >= min_score,
        )
        if exclude_dismissed:
            stmt = stmt.where(
                (MatchScore.user_feedback != UserFeedback.DISMISSED.value)
                | (MatchScore.user_feedback.is_(None))
            )
        stmt = stmt.order_by(desc(MatchScore.final_score), desc(MatchScore.scored_at))
        stmt = stmt.limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_match_score(
        self,
        opportunity_id: uuid.UUID,
        profile_id: uuid.UUID,
        final_score: float,
        eligibility_score: float,
        feature_overlap_score: float,
        semantic_similarity_score: float,
        weights_used: dict[str, Any],
        score_breakdown: dict[str, Any],
        explanation: str,
        user_feedback: UserFeedback | str | None = None,
        scored_at: Any | None = None,
    ) -> MatchScore:
        """
        Upsert a match score for an opportunity-profile pair.
        Ensures idempotency via unique constraint on (opportunity_id, profile_id).
        """
        feedback_val = (
            user_feedback.value
            if isinstance(user_feedback, UserFeedback)
            else (str(user_feedback) if user_feedback else None)
        )

        existing = await self.get_by_pair(opportunity_id, profile_id)
        if existing:
            existing.final_score = final_score
            existing.eligibility_score = eligibility_score
            existing.feature_overlap_score = feature_overlap_score
            existing.semantic_similarity_score = semantic_similarity_score
            existing.weights_used = weights_used
            existing.score_breakdown = score_breakdown
            existing.explanation = explanation
            if feedback_val is not None:
                existing.user_feedback = feedback_val
            if scored_at:
                existing.scored_at = scored_at
            await self.session.flush()
            return existing

        from datetime import UTC, datetime
        score = MatchScore(
            id=uuid.uuid4(),
            opportunity_id=opportunity_id,
            profile_id=profile_id,
            final_score=final_score,
            eligibility_score=eligibility_score,
            feature_overlap_score=feature_overlap_score,
            semantic_similarity_score=semantic_similarity_score,
            weights_used=weights_used,
            score_breakdown=score_breakdown,
            explanation=explanation,
            user_feedback=feedback_val,
            scored_at=scored_at or datetime.now(UTC),
        )
        self.session.add(score)
        await self.session.flush()
        return score

    async def update_feedback(
        self,
        opportunity_id: uuid.UUID,
        profile_id: uuid.UUID,
        feedback: UserFeedback | str,
    ) -> MatchScore | None:
        """Update user feedback on an existing match."""
        existing = await self.get_by_pair(opportunity_id, profile_id)
        if not existing:
            return None
        existing.user_feedback = feedback.value if isinstance(feedback, UserFeedback) else str(feedback)
        await self.session.flush()
        return existing

    async def delete_by_pair(
        self,
        opportunity_id: uuid.UUID,
        profile_id: uuid.UUID,
    ) -> bool:
        """Delete a match score by pair."""
        score = await self.get_by_pair(opportunity_id, profile_id)
        if not score:
            return False
        await self.session.delete(score)
        await self.session.flush()
        return True
