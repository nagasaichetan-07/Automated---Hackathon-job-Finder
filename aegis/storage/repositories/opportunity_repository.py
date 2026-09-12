"""
Aegis — Opportunity Repository

Async repository for persisting, upserting, and retrieving canonical opportunities.
Ensures idempotency across collection runs by matching on (source_id, external_id).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.schemas.domain import OpportunitySchema
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from storage.models.opportunity import Opportunity


class OpportunityRepository:
    """Async repository for canonical opportunity management."""

    @staticmethod
    async def get_by_id(session: AsyncSession, opp_id: uuid.UUID) -> Opportunity | None:
        """Fetch an opportunity by its internal primary key."""
        result = await session.execute(select(Opportunity).where(Opportunity.id == opp_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_external_id(
        session: AsyncSession,
        source_id: uuid.UUID,
        external_id: str,
    ) -> Opportunity | None:
        """Fetch an opportunity by its unique source external_id."""
        result = await session.execute(
            select(Opportunity).where(
                Opportunity.source_id == source_id,
                Opportunity.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_opportunity(
        session: AsyncSession,
        opp_data: OpportunitySchema | dict[str, Any],
    ) -> Opportunity:
        """
        Idempotently insert or update an opportunity record based on (source_id, external_id).
        """
        data = opp_data.model_dump() if isinstance(opp_data, OpportunitySchema) else dict(opp_data)
        source_id = data["source_id"]
        external_id = data["external_id"]

        existing = await OpportunityRepository.get_by_external_id(session, source_id, external_id)

        now = datetime.now(UTC)
        if existing:
            # Update mutable fields
            existing.title = data["title"]
            existing.category = getattr(data["category"], "value", str(data["category"]))
            existing.organizer = data.get("organizer")
            existing.url = data["url"]
            existing.description = data.get("description")
            existing.registration_deadline = data.get("registration_deadline")
            existing.start_date = data.get("start_date")
            existing.end_date = data.get("end_date")
            existing.location = data.get("location")
            mode_val = data.get("mode")
            existing.mode = getattr(mode_val, "value", str(mode_val)) if mode_val else None
            existing.eligibility_text = data.get("eligibility_text")
            existing.team_size_min = data.get("team_size_min")
            existing.team_size_max = data.get("team_size_max")
            existing.prize = data.get("prize")
            existing.skills_themes = data.get("skills_themes", [])
            existing.evidence = data.get("evidence", {})
            existing.content_hash = data.get("content_hash")
            existing.published_at = data.get("published_at")
            existing.collected_at = data.get("collected_at", now)
            await session.flush()
            return existing

        # Create new opportunity
        category_val = data.get("category", "job")
        mode_val = data.get("mode")
        opportunity = Opportunity(
            id=data.get("id") or uuid.uuid4(),
            source_id=source_id,
            external_id=external_id,
            title=data["title"],
            category=getattr(category_val, "value", str(category_val)),
            organizer=data.get("organizer"),
            url=data["url"],
            description=data.get("description"),
            registration_deadline=data.get("registration_deadline"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            location=data.get("location"),
            mode=getattr(mode_val, "value", str(mode_val)) if mode_val else None,
            eligibility_text=data.get("eligibility_text"),
            team_size_min=data.get("team_size_min"),
            team_size_max=data.get("team_size_max"),
            prize=data.get("prize"),
            skills_themes=data.get("skills_themes", []),
            evidence=data.get("evidence", {}),
            content_hash=data.get("content_hash"),
            published_at=data.get("published_at"),
            collected_at=data.get("collected_at", now),
        )
        session.add(opportunity)
        await session.flush()
        return opportunity

    @staticmethod
    async def list_opportunities(
        session: AsyncSession,
        source_id: uuid.UUID | None = None,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Opportunity]:
        """Query opportunities with optional source and category filters."""
        query = select(Opportunity)
        if source_id:
            query = query.where(Opportunity.source_id == source_id)
        if category:
            query = query.where(Opportunity.category == category)
        query = query.order_by(desc(Opportunity.collected_at)).offset(offset).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def count_opportunities(
        session: AsyncSession,
        source_id: uuid.UUID | None = None,
    ) -> int:
        """Count total opportunities in the store."""
        query = select(func.count(Opportunity.id))
        if source_id:
            query = query.where(Opportunity.source_id == source_id)
        result = await session.execute(query)
        return int(result.scalar() or 0)
