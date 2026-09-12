"""
Aegis — Eligibility Repository

Provides database access and upsert semantics for EligibilityDecision entities.
"""

from __future__ import annotations

import uuid
from typing import Any

from core.schemas.domain import EligibilityState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from storage.models.eligibility_decision import EligibilityDecision


class EligibilityRepository:
    """Repository managing EligibilityDecision persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, decision_id: uuid.UUID) -> EligibilityDecision | None:
        """Fetch eligibility decision by primary key ID."""
        stmt = select(EligibilityDecision).where(EligibilityDecision.id == decision_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_pair(
        self,
        opportunity_id: uuid.UUID,
        profile_id: uuid.UUID,
    ) -> EligibilityDecision | None:
        """Fetch decision for a specific opportunity-profile pair."""
        stmt = select(EligibilityDecision).where(
            EligibilityDecision.opportunity_id == opportunity_id,
            EligibilityDecision.profile_id == profile_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_profile(
        self,
        profile_id: uuid.UUID,
        state_filter: EligibilityState | None = None,
    ) -> list[EligibilityDecision]:
        """Fetch all decisions for a profile, optionally filtered by state."""
        stmt = select(EligibilityDecision).where(EligibilityDecision.profile_id == profile_id)
        if state_filter is not None:
            stmt = stmt.where(EligibilityDecision.state == state_filter.value)
        stmt = stmt.order_by(EligibilityDecision.evaluated_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_decision(
        self,
        opportunity_id: uuid.UUID,
        profile_id: uuid.UUID,
        state: EligibilityState,
        evidence: dict[str, Any],
        rule_results: dict[str, Any],
        confidence: float | None = None,
        evaluated_at: Any | None = None,
    ) -> EligibilityDecision:
        """
        Upsert an eligibility decision for an opportunity-profile pair.
        Ensures idempotency via unique constraint on (opportunity_id, profile_id).
        """
        existing = await self.get_by_pair(opportunity_id, profile_id)
        if existing:
            existing.state = state.value if isinstance(state, EligibilityState) else str(state)
            existing.evidence = evidence
            existing.rule_results = rule_results
            existing.confidence = confidence
            if evaluated_at:
                existing.evaluated_at = evaluated_at
            await self.session.flush()
            return existing

        from datetime import UTC, datetime
        decision = EligibilityDecision(
            id=uuid.uuid4(),
            opportunity_id=opportunity_id,
            profile_id=profile_id,
            state=state.value if isinstance(state, EligibilityState) else str(state),
            evidence=evidence,
            rule_results=rule_results,
            confidence=confidence,
            evaluated_at=evaluated_at or datetime.now(UTC),
        )
        self.session.add(decision)
        await self.session.flush()
        return decision

    async def delete_by_pair(
        self,
        opportunity_id: uuid.UUID,
        profile_id: uuid.UUID,
    ) -> bool:
        """Delete an eligibility decision by pair."""
        decision = await self.get_by_pair(opportunity_id, profile_id)
        if not decision:
            return False
        await self.session.delete(decision)
        await self.session.flush()
        return True
