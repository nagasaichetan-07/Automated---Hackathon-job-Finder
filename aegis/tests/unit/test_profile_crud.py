"""
Aegis — Profile CRUD & Draft-to-Authoritative Lifecycle Tests

Tests the complete profile lifecycle:
1. Profile creation via repository
2. Résumé upload saving as unconfirmed draft (resume_confirmed=False)
3. Explicit confirmation promoting draft to authoritative (resume_confirmed=True)
4. Profile update operations
5. API endpoint integration via HTTPX test client
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from storage.models.base import Base
from storage.repositories.profile_repository import ProfileRepository

# ---------------------------------------------------------------------------
# Fixtures: in-memory async SQLite engine for isolated tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def async_engine():
    """Create a disposable async SQLite engine for test isolation."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(async_engine):
    """Provide a clean async session for each test."""
    session_factory = async_sessionmaker(bind=async_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Tests: Profile Creation
# ---------------------------------------------------------------------------


class TestProfileCreation:
    """Test creating profiles via the repository."""

    @pytest.mark.asyncio
    async def test_create_new_profile(self, db_session) -> None:
        """Create a new profile and verify all fields are set."""
        user_id = uuid.uuid4()
        profile = await ProfileRepository.create_or_update(
            db_session,
            user_id=user_id,
            profile_data={
                "education_level": "B.Tech",
                "graduation_year": 2026,
                "branch": "Computer Science",
                "skills": ["Python", "SQL"],
                "preferred_locations": ["Remote", "Bangalore"],
                "opportunity_types": ["internship", "job"],
                "interests": ["Machine Learning"],
                "constraints": {"min_stipend": 10000},
            },
        )
        await db_session.commit()

        assert profile.user_id == user_id
        assert profile.education_level == "B.Tech"
        assert profile.graduation_year == 2026
        assert profile.branch == "Computer Science"
        assert "Python" in profile.skills
        assert profile.resume_confirmed is False  # No résumé uploaded yet

    @pytest.mark.asyncio
    async def test_create_profile_with_skill_normalization(self, db_session) -> None:
        """Skills are normalized via the alias table on creation."""
        user_id = uuid.uuid4()
        profile = await ProfileRepository.create_or_update(
            db_session,
            user_id=user_id,
            profile_data={
                "skills": ["JS", "Postgres", "Py", "react", "k8s"],
            },
        )
        await db_session.commit()

        assert "JavaScript" in profile.skills
        assert "PostgreSQL" in profile.skills
        assert "Python" in profile.skills
        assert "React" in profile.skills
        assert "Kubernetes" in profile.skills

    @pytest.mark.asyncio
    async def test_update_existing_profile(self, db_session) -> None:
        """Updating an existing profile modifies only the specified fields."""
        user_id = uuid.uuid4()
        # Create
        await ProfileRepository.create_or_update(
            db_session,
            user_id=user_id,
            profile_data={
                "education_level": "B.Tech",
                "graduation_year": 2025,
                "skills": ["Python"],
            },
        )
        await db_session.flush()

        # Update only graduation year
        profile = await ProfileRepository.create_or_update(
            db_session,
            user_id=user_id,
            profile_data={"graduation_year": 2026},
        )
        await db_session.commit()

        assert profile.graduation_year == 2026
        assert profile.education_level == "B.Tech"  # Unchanged


# ---------------------------------------------------------------------------
# Tests: Résumé Draft Lifecycle
# ---------------------------------------------------------------------------


class TestResumeDraftLifecycle:
    """Test the draft-to-authoritative confirmation workflow."""

    @pytest.mark.asyncio
    async def test_save_resume_draft_sets_unconfirmed(self, db_session) -> None:
        """Saving a résumé draft must set resume_confirmed = False."""
        user_id = uuid.uuid4()
        profile = await ProfileRepository.save_resume_draft(
            db_session,
            user_id=user_id,
            raw_text="John Doe B.Tech Computer Science 2026 Python SQL Docker",
            extracted_data={
                "education_level": "B.Tech",
                "graduation_year": 2026,
                "skills": ["Python", "SQL", "Docker"],
            },
            evidence_data={
                "education_level": {"evidence": "B.Tech", "confidence": 0.92},
                "graduation_year": {"evidence": "2026", "confidence": 0.95},
            },
        )
        await db_session.commit()

        assert profile.resume_confirmed is False
        assert profile.resume_raw_text is not None
        assert profile.resume_extracted is not None
        assert profile.resume_evidence is not None
        # Authoritative fields should NOT be populated from draft
        assert profile.education_level is None
        assert profile.graduation_year is None

    @pytest.mark.asyncio
    async def test_draft_does_not_set_authoritative_fields(self, db_session) -> None:
        """
        Draft extraction must NOT alter authoritative profile fields.
        This is the critical invariant per Phase 2 requirements.
        """
        user_id = uuid.uuid4()
        # First set authoritative data
        await ProfileRepository.create_or_update(
            db_session,
            user_id=user_id,
            profile_data={
                "education_level": "B.S.",
                "skills": ["Java"],
            },
        )
        await db_session.flush()

        # Now upload a résumé draft with different data
        profile = await ProfileRepository.save_resume_draft(
            db_session,
            user_id=user_id,
            raw_text="M.Tech Data Science Python TensorFlow",
            extracted_data={
                "education_level": "M.Tech",
                "skills": ["Python", "TensorFlow"],
            },
            evidence_data={},
        )
        await db_session.commit()

        # Authoritative fields should be UNCHANGED
        assert profile.education_level == "B.S."
        assert "Java" in profile.skills
        # Draft is stored separately
        assert profile.resume_extracted is not None
        assert profile.resume_extracted["education_level"] == "M.Tech"
        assert profile.resume_confirmed is False

    @pytest.mark.asyncio
    async def test_confirm_profile_sets_authoritative(self, db_session) -> None:
        """Confirming draft fields promotes them to authoritative status."""
        user_id = uuid.uuid4()
        # Save draft first
        await ProfileRepository.save_resume_draft(
            db_session,
            user_id=user_id,
            raw_text="B.Tech CS 2026 Python Docker",
            extracted_data={
                "education_level": "B.Tech",
                "graduation_year": 2026,
                "skills": ["Python", "Docker"],
            },
            evidence_data={},
        )
        await db_session.flush()

        # User reviews and confirms
        profile = await ProfileRepository.confirm_profile(
            db_session,
            user_id=user_id,
            confirmed_fields={
                "education_level": "B.Tech",
                "graduation_year": 2026,
                "skills": ["Python", "Docker", "SQL"],
                "preferred_locations": ["Remote"],
            },
        )
        await db_session.commit()

        assert profile.resume_confirmed is True
        assert profile.education_level == "B.Tech"
        assert profile.graduation_year == 2026
        assert "Python" in profile.skills
        assert "Docker" in profile.skills
        assert "SQL" in profile.skills
        assert "Remote" in profile.preferred_locations


# ---------------------------------------------------------------------------
# Tests: API Endpoint Integration
# ---------------------------------------------------------------------------


class TestProfileAPIEndpoints:
    """Test profile API endpoints via the HTTPX async test client."""

    @pytest.fixture
    def app(self, async_engine):
        """Create a test FastAPI app with overridden DB dependency."""
        from apps.api.main import create_app
        from storage.database import get_db_session

        test_app = create_app()

        # Override DB session dependency
        session_factory = async_sessionmaker(bind=async_engine, expire_on_commit=False)

        async def override_get_db_session():
            async with session_factory() as session:
                yield session

        test_app.dependency_overrides[get_db_session] = override_get_db_session
        return test_app

    @pytest.mark.asyncio
    async def test_create_profile_endpoint(self, app) -> None:
        """POST /api/v1/profile creates a new profile."""
        user_id = str(uuid.uuid4())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/v1/profile?user_id={user_id}",
                json={
                    "education_level": "B.Tech",
                    "graduation_year": 2026,
                    "branch": "Computer Science",
                    "skills": ["Python", "JS"],
                },
            )
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == user_id
        assert data["education_level"] == "B.Tech"
        assert data["resume_confirmed"] is False
        # Skills should be normalized
        assert "JavaScript" in data["skills"]

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, app) -> None:
        """GET /api/v1/profile/{user_id} returns 404 for non-existent profile."""
        fake_id = str(uuid.uuid4())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/profile/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_confirm_endpoint_sets_authoritative(self, app) -> None:
        """POST /api/v1/profile/{user_id}/confirm sets resume_confirmed=True."""
        user_id = str(uuid.uuid4())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Create profile first
            await client.post(
                f"/api/v1/profile?user_id={user_id}",
                json={"education_level": "B.Tech", "skills": ["Python"]},
            )

            # Confirm
            response = await client.post(
                f"/api/v1/profile/{user_id}/confirm",
                json={
                    "education_level": "B.Tech",
                    "graduation_year": 2026,
                    "skills": ["Python", "Docker"],
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["resume_confirmed"] is True
        assert data["graduation_year"] == 2026
