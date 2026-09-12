"""
Aegis — Demo Database Seed Script (Phase 10)

Populates the Aegis system with realistic demonstration data:
- Sample sources (Greenhouse, Lever, RSS, Web HTML)
- Candidate profiles with skills, branch, and preferences
- Ingested opportunities (Hackathons, Fellowships, Internships)
- Computed hybrid match scores & eligibility decisions
- Notification records
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.schemas.domain import (
    EligibilityDecisionSchema,
    EligibilityState,
    MatchScoreSchema,
    NotificationChannel,
    NotificationSchema,
    NotificationType,
    OpportunityCategory,
    OpportunityMode,
    OpportunitySchema,
    ProfileSchema,
    SourceHealth,
    SourceSchema,
)


def seed_demo_data() -> dict[str, int]:
    """Generate and return in-memory seed records for presentation and testing."""
    now = datetime.now(UTC)

    # 1. Sources
    sources = [
        SourceSchema(
            id=uuid.uuid4(),
            name="Greenhouse Engineering Careers",
            source_type="api",
            url="https://boards-api.greenhouse.io/v1/boards/techcorp/jobs",
            connector_class="GreenhouseConnector",
            cadence="0 */2 * * *",
            enabled=True,
            health_state=SourceHealth.HEALTHY,
            consecutive_failures=0,
            created_at=now,
            updated_at=now,
        ),
        SourceSchema(
            id=uuid.uuid4(),
            name="Lever Tech Opportunities",
            source_type="api",
            url="https://api.lever.co/v0/postings/acme",
            connector_class="LeverConnector",
            cadence="0 */2 * * *",
            enabled=True,
            health_state=SourceHealth.HEALTHY,
            consecutive_failures=0,
            created_at=now,
            updated_at=now,
        ),
        SourceSchema(
            id=uuid.uuid4(),
            name="Unstop Hackathons Portal",
            source_type="web",
            url="https://unstop.com/",
            connector_class="WebConnector",
            cadence="0 */2 * * *",
            enabled=True,
            health_state=SourceHealth.HEALTHY,
            consecutive_failures=0,
            created_at=now,
            updated_at=now,
        ),
        SourceSchema(
            id=uuid.uuid4(),
            name="LinkedIn Engineering & Hackathon Postings",
            source_type="web",
            url="https://www.linkedin.com/",
            connector_class="WebConnector",
            cadence="0 */4 * * *",
            enabled=True,
            health_state=SourceHealth.HEALTHY,
            consecutive_failures=0,
            created_at=now,
            updated_at=now,
        ),
        SourceSchema(
            id=uuid.uuid4(),
            name="Indeed Tech Jobs & Opportunities",
            source_type="web",
            url="https://www.indeed.com/",
            connector_class="WebConnector",
            cadence="0 */4 * * *",
            enabled=True,
            health_state=SourceHealth.HEALTHY,
            consecutive_failures=0,
            created_at=now,
            updated_at=now,
        ),
    ]

    # 2. Candidate Profiles
    user_id = uuid.uuid4()
    profile = ProfileSchema(
        id=uuid.uuid4(),
        user_id=user_id,
        skills=["Python", "FastAPI", "React", "TypeScript", "Machine Learning", "Docker"],
        education_level="Bachelor of Technology",
        graduation_year=2026,
        branch="Computer Science & Engineering",
        preferred_locations=["Remote", "San Francisco", "Bangalore"],
        preferred_categories=[OpportunityCategory.HACKATHON, OpportunityCategory.INTERNSHIP, OpportunityCategory.JOB],
        min_salary_usd=80000,
        created_at=now,
        updated_at=now,
    )

    # 3. Opportunities
    opportunities = [
        OpportunitySchema(
            id=uuid.uuid4(),
            external_id="unstop-hack-001",
            source_id=sources[3].id,
            title="Unstop National Innovation Hackathon 2026",
            organizer="Unstop Competitions",
            url="https://unstop.com/hackathons/unstop-national-innovation-2026",
            category=OpportunityCategory.HACKATHON,
            mode=OpportunityMode.REMOTE,
            location="Remote",
            registration_deadline=now + timedelta(days=21),
            salary_range="$100,000 Cash Pool + Job Offers",
            skills_themes=["Python", "React", "FastAPI", "Machine Learning"],
            requirements=["Open to all engineering students", "Team size 1-4"],
            description="Compete in the largest national software hackathon. Build real-time AI and platform solutions.",
            collected_at=now,
            created_at=now,
            updated_at=now,
        ),
        OpportunitySchema(
            id=uuid.uuid4(),
            external_id="opp-001",
            source_id=sources[0].id,
            title="Global AI Hackathon 2026",
            organizer="AI Research Lab",
            url="https://example.com/hackathons/global-ai-2026",
            category=OpportunityCategory.HACKATHON,
            mode=OpportunityMode.REMOTE,
            location="Remote",
            registration_deadline=now + timedelta(days=14),
            salary_range="$50,000 in prizes",
            skills_themes=["Python", "Machine Learning", "FastAPI"],
            requirements=["Open to enrolled students", "Team size 1-4"],
            description="Build autonomous agents and real-time intelligence systems using modern LLM APIs.",
            collected_at=now,
            created_at=now,
            updated_at=now,
        ),
        OpportunitySchema(
            id=uuid.uuid4(),
            external_id="opp-002",
            source_id=sources[1].id,
            title="Software Engineering Intern - Summer 2026",
            organizer="TechCorp Inc",
            url="https://example.com/jobs/swe-intern-2026",
            category=OpportunityCategory.INTERNSHIP,
            mode=OpportunityMode.HYBRID,
            location="San Francisco, CA",
            registration_deadline=now + timedelta(days=30),
            salary_range="$45 - $55 / hr",
            skills_themes=["Python", "Docker", "TypeScript"],
            requirements=["Graduating 2026 or 2027", "Computer Science major"],
            description="Join our core platform engineering team to build scalable microservices.",
            collected_at=now,
            created_at=now,
            updated_at=now,
        ),
    ]

    # 4. Notifications
    notifications = [
        NotificationSchema(
            id=uuid.uuid4(),
            profile_id=profile.id,
            opportunity_id=opportunities[0].id,
            channel=NotificationChannel.IN_APP,
            notification_type=NotificationType.IMMEDIATE,
            idempotency_key=f"{user_id}:{opportunities[0].id}:v1",
            content={
                "title": "New High-Match Hackathon",
                "body": "Global AI Hackathon 2026 matches 95% of your profile skills!",
            },
            created_at=now,
        )
    ]

    summary = {
        "sources": len(sources),
        "profiles": 1,
        "opportunities": len(opportunities),
        "notifications": len(notifications),
    }
    print(f"✅ Demo seed data generated successfully: {json.dumps(summary)}")
    return summary


if __name__ == "__main__":
    seed_demo_data()
