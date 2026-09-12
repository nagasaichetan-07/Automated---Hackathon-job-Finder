"""
Aegis — Profile Repository

Data access and lifecycle management for student profiles.
Enforces the draft-vs-authoritative invariant:
extracted résumé fields remain unconfirmed drafts until explicitly committed via confirm_profile().
"""

from __future__ import annotations

import uuid
from typing import Any

from normalization.skills import normalize_skills
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from storage.models.profile import Profile


class ProfileRepository:
    """Repository managing Profile persistence and lifecycle transitions."""

    @staticmethod
    async def get_by_id(session: AsyncSession, profile_id: uuid.UUID) -> Profile | None:
        """Fetch profile by primary key UUID."""
        stmt = select(Profile).where(Profile.id == profile_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_user_id(session: AsyncSession, user_id: uuid.UUID) -> Profile | None:
        """Fetch profile by user UUID."""
        stmt = select(Profile).where(Profile.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_or_update(
        session: AsyncSession,
        user_id: uuid.UUID,
        profile_data: dict[str, Any],
    ) -> Profile:
        """
        Create a new profile or update existing profile facts directly.
        """
        profile = await ProfileRepository.get_by_user_id(session, user_id)
        if profile is None:
            profile = Profile(user_id=user_id)
            session.add(profile)

        # Apply authoritative fields
        if "education_level" in profile_data:
            profile.education_level = profile_data["education_level"]
        if "graduation_year" in profile_data:
            profile.graduation_year = profile_data["graduation_year"]
        if "branch" in profile_data:
            profile.branch = profile_data["branch"]
        if "skills" in profile_data:
            profile.skills = normalize_skills(profile_data["skills"])
        if "preferred_locations" in profile_data:
            profile.preferred_locations = profile_data["preferred_locations"]
        if "opportunity_types" in profile_data:
            profile.opportunity_types = profile_data["opportunity_types"]
        if "interests" in profile_data:
            profile.interests = profile_data["interests"]
        if "constraints" in profile_data:
            profile.constraints = profile_data["constraints"]

        await session.flush()
        return profile

    @staticmethod
    async def save_resume_draft(
        session: AsyncSession,
        user_id: uuid.UUID,
        raw_text: str,
        extracted_data: dict[str, Any],
        evidence_data: dict[str, Any],
    ) -> Profile:
        """
        Persist extracted résumé text and draft fields.
        INVARIANT: Sets resume_confirmed = False.
        Does NOT alter authoritative profile fields until confirmed.
        """
        profile = await ProfileRepository.get_by_user_id(session, user_id)
        if profile is None:
            profile = Profile(user_id=user_id)
            session.add(profile)

        profile.resume_raw_text = raw_text
        profile.resume_extracted = extracted_data
        profile.resume_evidence = evidence_data
        profile.resume_confirmed = False  # Strictly DRAFT until confirmed

        await session.flush()
        return profile

    @staticmethod
    async def confirm_profile(
        session: AsyncSession,
        user_id: uuid.UUID,
        confirmed_fields: dict[str, Any],
    ) -> Profile:
        """
        Authoritatively commit user-reviewed draft fields to the active profile.
        INVARIANT: Sets resume_confirmed = True.
        """
        profile = await ProfileRepository.get_by_user_id(session, user_id)
        if profile is None:
            profile = Profile(user_id=user_id)
            session.add(profile)

        if "education_level" in confirmed_fields:
            profile.education_level = confirmed_fields["education_level"]
        if "graduation_year" in confirmed_fields:
            profile.graduation_year = confirmed_fields["graduation_year"]
        if "branch" in confirmed_fields:
            profile.branch = confirmed_fields["branch"]
        if "skills" in confirmed_fields:
            profile.skills = normalize_skills(confirmed_fields["skills"])
        if "preferred_locations" in confirmed_fields:
            profile.preferred_locations = confirmed_fields["preferred_locations"]
        if "opportunity_types" in confirmed_fields:
            profile.opportunity_types = confirmed_fields["opportunity_types"]
        if "interests" in confirmed_fields:
            profile.interests = confirmed_fields["interests"]

        profile.resume_confirmed = True  # Now authoritative
        await session.flush()
        return profile

    @staticmethod
    async def list_all_confirmed(session: AsyncSession) -> list[Profile]:
        """Fetch all profiles where resume_confirmed is True."""
        stmt = select(Profile).where(Profile.resume_confirmed.is_(True))
        result = await session.execute(stmt)
        return list(result.scalars().all())
