"""
Aegis — Scan & Register Live Opportunities Script

Crawls live hackathons and internships from target platforms (Unstop, Greenhouse, Lever),
ranks them against candidate profiles, and saves them to the database repository
with direct, exact opportunity URLs.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from connectors.live_crawler import LiveOpportunityCrawler
from core.schemas.domain import ProfileSchema, OpportunitySchema
from opportunity.ranking.engine import RankingEngine
from storage.database import AsyncSessionLocal
from storage.repositories.eligibility_repository import EligibilityRepository
from storage.repositories.match_repository import MatchRepository
from storage.repositories.opportunity_repository import OpportunityRepository
from storage.repositories.profile_repository import ProfileRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def scan_and_register_live_opportunities():
    """Crawl, rank, and store real live hackathons and internships."""
    print("\n=======================================================")
    print("🔍 AEGIS REAL-TIME LIVE CRAWLER RUNNING...")
    print("=======================================================")
    crawler = LiveOpportunityCrawler()
    live_opps = await crawler.fetch_all_live_opportunities()
    print(f"\n✅ Extracted {len(live_opps)} total live opportunities with direct exact URLs.")

    async with AsyncSessionLocal() as db:
        elig_repo = EligibilityRepository(db)
        match_repo = MatchRepository(db)

        # 1. Fetch default profile or create candidate profile
        db_profile = await ProfileRepository.get_by_user_id(db, DEFAULT_USER_ID)
        if not db_profile:
            db_profile = await ProfileRepository.create_or_update(
                db,
                user_id=DEFAULT_USER_ID,
                profile_data={
                    "education_level": "Bachelor of Technology",
                    "graduation_year": 2026,
                    "branch": "Computer Science & Engineering",
                    "skills": ["Python", "FastAPI", "React", "TypeScript", "Machine Learning", "Software Engineering"],
                    "preferred_locations": ["Remote", "San Francisco", "Online / Remote"],
                },
            )
            await db.commit()

        # Convert to ProfileSchema for RankingEngine
        candidate_profile = ProfileSchema(
            id=db_profile.id,
            user_id=db_profile.user_id,
            skills=db_profile.skills or ["Python", "React", "FastAPI"],
            education_level=db_profile.education_level or "Bachelor of Technology",
            graduation_year=db_profile.graduation_year or 2026,
            branch=db_profile.branch or "Computer Science",
            preferred_locations=db_profile.preferred_locations or ["Remote"],
            preferred_categories=[],
            min_salary_usd=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # 2. Store live opportunities in DB using upsert
        saved_opp_schemas: list[OpportunitySchema] = []
        for opp in live_opps:
            opp_db_model = await OpportunityRepository.upsert_opportunity(db, opp)
            saved_opp = OpportunitySchema(
                id=opp_db_model.id,
                external_id=opp_db_model.external_id,
                source_id=opp_db_model.source_id,
                title=opp_db_model.title,
                organizer=opp_db_model.organizer,
                url=opp_db_model.url,
                category=opp.category,
                mode=opp.mode,
                location=opp_db_model.location,
                registration_deadline=opp_db_model.registration_deadline,
                salary_range=opp.salary_range if hasattr(opp, 'salary_range') else opp_db_model.prize,
                skills_themes=opp_db_model.skills_themes or ["Tech", "Software"],
                requirements=["Open to enrolled students"],
                description=opp_db_model.description,
                collected_at=opp_db_model.collected_at or datetime.now(UTC),
                created_at=opp_db_model.published_at or datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            saved_opp_schemas.append(saved_opp)

        await db.commit()

        # 3. Rank live opportunities against candidate profile
        engine = RankingEngine()
        ranked_results = engine.rank_opportunities(candidate_profile, saved_opp_schemas)

        # 4. Save match scores & eligibility decisions
        for opp_schema, score_schema, elig_schema in ranked_results:
            await elig_repo.save_decision(
                opportunity_id=opp_schema.id,
                profile_id=candidate_profile.id,
                state=elig_schema.state,
                evidence=elig_schema.evidence,
                rule_results=elig_schema.rule_results,
                confidence=elig_schema.confidence,
            )
            await match_repo.save_match_score(
                opportunity_id=opp_schema.id,
                profile_id=candidate_profile.id,
                final_score=score_schema.final_score,
                eligibility_score=score_schema.eligibility_score,
                feature_overlap_score=score_schema.feature_overlap_score,
                semantic_similarity_score=score_schema.semantic_similarity_score,
                weights_used=score_schema.weights_used,
                score_breakdown=score_schema.score_breakdown,
                explanation=score_schema.explanation,
            )
        await db.commit()

        print(f"\n🎉 Successfully saved and ranked {len(ranked_results)} live opportunities in database.")
        print("\n=======================================================")
        print("TOP 10 LIVE EXTRACTED HACKATHONS & INTERNSHIPS:")
        print("=======================================================")
        for opp_schema, score_schema, elig_schema in ranked_results[:10]:
            score_pct = int(score_schema.final_score * 100)
            print(f" • [{elig_schema.state} | {score_pct}% Match] {opp_schema.title}")
            print(f"   Organizer: {opp_schema.organizer} | Type: {opp_schema.category.value.upper()}")
            print(f"   Direct Opportunity Link: {opp_schema.url}\n")


if __name__ == "__main__":
    asyncio.run(scan_and_register_live_opportunities())
