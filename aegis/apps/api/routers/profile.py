"""
Aegis — Profile & Résumé Intelligence API Router

Provides endpoints for profile management, résumé PDF upload,
two-stage deterministic & structured extraction, and explicit user confirmation.
"""

from __future__ import annotations

import uuid
from typing import Any

from extraction.deterministic.pdf_extractor import (
    FileSizeLimitExceededError,
    InvalidFileTypeError,
    MalformedPDFError,
    extract_text_from_pdf_bytes,
)
from extraction.llm.resume_extractor import extract_resume_data
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from storage.database import get_db_session
from storage.repositories.profile_repository import ProfileRepository

router = APIRouter(prefix="/api/v1/profile", tags=["Profile & Résumé Intelligence"])


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------


class ProfileUpdateRequest(BaseModel):
    """Payload for updating authoritative profile fields directly."""

    education_level: str | None = None
    graduation_year: int | None = None
    branch: str | None = None
    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    opportunity_types: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class ProfileConfirmRequest(BaseModel):
    """Payload for confirming draft résumé fields as authoritative."""

    education_level: str | None = None
    graduation_year: int | None = None
    branch: str | None = None
    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    opportunity_types: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    """Full profile response representation."""

    id: uuid.UUID
    user_id: uuid.UUID
    education_level: str | None = None
    graduation_year: int | None = None
    branch: str | None = None
    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    opportunity_types: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    resume_confirmed: bool = False
    resume_extracted: dict[str, Any] | None = None
    resume_evidence: dict[str, Any] | None = None


class ResumeUploadResponse(BaseModel):
    """Response returned upon résumé upload and extraction."""

    status: str = "draft_extracted"
    message: str = (
        "Résumé extracted into draft fields. Review and confirm to apply to your profile."
    )
    draft_fields: dict[str, Any]
    evidence: dict[str, Any]
    char_count: int
    page_count: int
    is_confirmed: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_or_init_profile(
    user_id: uuid.UUID,
    payload: ProfileUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProfileResponse:
    """Create or initialize a student profile."""
    profile = await ProfileRepository.create_or_update(
        session,
        user_id=user_id,
        profile_data=payload.model_dump(),
    )
    return ProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        education_level=profile.education_level,
        graduation_year=profile.graduation_year,
        branch=profile.branch,
        skills=profile.skills,
        preferred_locations=profile.preferred_locations,
        opportunity_types=profile.opportunity_types,
        interests=profile.interests,
        constraints=profile.constraints,
        resume_confirmed=profile.resume_confirmed,
        resume_extracted=profile.resume_extracted,
        resume_evidence=profile.resume_evidence,
    )


@router.get("/{user_id}", response_model=ProfileResponse)
async def get_profile(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> ProfileResponse:
    """Retrieve profile by user ID."""
    profile = await ProfileRepository.get_by_user_id(session, user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile for user_id '{user_id}' not found.",
        )
    return ProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        education_level=profile.education_level,
        graduation_year=profile.graduation_year,
        branch=profile.branch,
        skills=profile.skills,
        preferred_locations=profile.preferred_locations,
        opportunity_types=profile.opportunity_types,
        interests=profile.interests,
        constraints=profile.constraints,
        resume_confirmed=profile.resume_confirmed,
        resume_extracted=profile.resume_extracted,
        resume_evidence=profile.resume_evidence,
    )


@router.put("/{user_id}", response_model=ProfileResponse)
async def update_profile(
    user_id: uuid.UUID,
    payload: ProfileUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProfileResponse:
    """Directly update profile facts."""
    profile = await ProfileRepository.create_or_update(
        session,
        user_id=user_id,
        profile_data=payload.model_dump(),
    )
    return ProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        education_level=profile.education_level,
        graduation_year=profile.graduation_year,
        branch=profile.branch,
        skills=profile.skills,
        preferred_locations=profile.preferred_locations,
        opportunity_types=profile.opportunity_types,
        interests=profile.interests,
        constraints=profile.constraints,
        resume_confirmed=profile.resume_confirmed,
        resume_extracted=profile.resume_extracted,
        resume_evidence=profile.resume_evidence,
    )


@router.post("/{user_id}/resume", response_model=ResumeUploadResponse)
async def upload_resume(
    user_id: uuid.UUID,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> ResumeUploadResponse:
    """
    Upload résumé PDF, extract text deterministically, and structure draft fields.
    Guarantees:
    - Enforces MIME, magic bytes, and size checks.
    - Saves extraction strictly as an unconfirmed DRAFT.
    - Neutralizes any prompt injection instructions.
    """
    file_bytes = await file.read()

    # 1. Deterministic Extraction & Validation
    try:
        extraction_result = extract_text_from_pdf_bytes(
            file_bytes=file_bytes,
            content_type=file.content_type,
        )
    except FileSizeLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    except InvalidFileTypeError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc
    except MalformedPDFError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # 2. Structured Extraction on Extracted Text
    draft = extract_resume_data(extraction_result.raw_text)

    # 3. Store draft into repository (resume_confirmed = False)
    draft_dict = {
        "education_level": draft.education_level,
        "graduation_year": draft.graduation_year,
        "branch": draft.branch,
        "skills": draft.skills,
        "preferred_locations": draft.preferred_locations,
        "opportunity_types": draft.opportunity_types,
        "interests": draft.interests,
    }
    evidence_dict = {
        k: {"value": v.value, "evidence": v.evidence, "confidence": v.confidence}
        for k, v in draft.evidence.items()
    }

    await ProfileRepository.save_resume_draft(
        session,
        user_id=user_id,
        raw_text=extraction_result.raw_text,
        extracted_data=draft_dict,
        evidence_data=evidence_dict,
    )

    return ResumeUploadResponse(
        draft_fields=draft_dict,
        evidence=evidence_dict,
        char_count=extraction_result.char_count,
        page_count=extraction_result.page_count,
        is_confirmed=False,
    )


@router.post("/{user_id}/confirm", response_model=ProfileResponse)
async def confirm_resume_profile(
    user_id: uuid.UUID,
    payload: ProfileConfirmRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProfileResponse:
    """
    Authoritatively commit user-reviewed draft fields to the active profile.
    Sets resume_confirmed = True.
    """
    profile = await ProfileRepository.confirm_profile(
        session,
        user_id=user_id,
        confirmed_fields=payload.model_dump(),
    )
    return ProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        education_level=profile.education_level,
        graduation_year=profile.graduation_year,
        branch=profile.branch,
        skills=profile.skills,
        preferred_locations=profile.preferred_locations,
        opportunity_types=profile.opportunity_types,
        interests=profile.interests,
        constraints=profile.constraints,
        resume_confirmed=profile.resume_confirmed,
        resume_extracted=profile.resume_extracted,
        resume_evidence=profile.resume_evidence,
    )
