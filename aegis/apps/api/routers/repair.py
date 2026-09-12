"""
Aegis — Self-Healing Repair API Router

Endpoints for inspecting repair runs, viewing unified diff candidates, approving/rejecting patches,
triggering manual repairs, and performing instant rollbacks.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from agents.orchestrator.repair_orchestrator import RepairOrchestrator
from core.schemas.domain import FailureClass, RepairRunOutcome, RepairState, RepairTriggerType
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from storage.database import get_db_session
from storage.repositories.repair_repository import RepairRepository

router = APIRouter(prefix="/api/v1/repair", tags=["Self-Healing Repair"])


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------


class TriggerRepairRequest(BaseModel):
    """Payload to trigger a self-healing repair run."""

    source_id: uuid.UUID
    target_file_rel: str = Field(..., min_length=1)
    failure_class: str = Field(default="selector_not_found")
    error_summary: str | None = None
    raw_snapshot: str | None = None
    broken_selector: str | None = None
    fixed_selector: str | None = None
    test_pattern: str | None = None


class PatchApproveRequest(BaseModel):
    """Payload to approve and promote a patch."""

    approved_by: str = Field(default="human_admin")


class PatchRejectRequest(BaseModel):
    """Payload to reject a proposed patch."""

    reason: str = Field(..., min_length=1)


class PatchRollbackRequest(BaseModel):
    """Payload to roll back a promoted patch."""

    reason: str = Field(default="Manual rollback triggered")


class RepairPatchResponse(BaseModel):
    """Public schema for a proposed/promoted patch."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repair_run_id: uuid.UUID
    state: str
    target_file: str
    diff_content: str
    sandbox_passed: bool
    test_results: dict[str, Any]
    validation_results: dict[str, Any]
    approved_by: str | None
    connector_version_before: str | None
    connector_version_after: str | None
    rejection_reason: str | None
    proposed_at: datetime
    tested_at: datetime | None
    promoted_at: datetime | None
    rolled_back_at: datetime | None


class RepairRunResponse(BaseModel):
    """Public schema for a repair run audit record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    trigger_type: str
    failure_class: str
    error_summary: str | None
    diagnosis: dict[str, Any]
    outcome: str | None
    started_at: datetime
    completed_at: datetime | None
    patches: list[RepairPatchResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/runs", response_model=list[RepairRunResponse], summary="List repair runs")
async def list_repair_runs(
    source_id: uuid.UUID | None = Query(None, description="Filter by source ID"),
    outcome: str | None = Query(None, description="Filter by run outcome"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[RepairRunResponse]:
    """List all repair runs ordered by start time descending."""
    repo = RepairRepository(session)
    runs = await repo.list_runs(source_id=source_id, outcome=outcome, limit=limit, offset=offset)
    return [RepairRunResponse.model_validate(r) for r in runs]


@router.get("/runs/{run_id}", response_model=RepairRunResponse, summary="Get repair run details")
async def get_repair_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> RepairRunResponse:
    """Retrieve detailed information and patches for a specific repair run."""
    repo = RepairRepository(session)
    run = await repo.get_run_by_id(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repair run with id '{run_id}' not found",
        )
    return RepairRunResponse.model_validate(run)


@router.post("/trigger", response_model=RepairRunResponse, status_code=status.HTTP_201_CREATED, summary="Trigger self-healing repair run")
async def trigger_repair_run(
    payload: TriggerRepairRequest,
    session: AsyncSession = Depends(get_db_session),
) -> RepairRunResponse:
    """Trigger the self-healing pipeline for a broken connector."""
    orchestrator = RepairOrchestrator(session)
    run, patch = await orchestrator.execute_self_healing_run(
        source_id=payload.source_id,
        target_file_rel=payload.target_file_rel,
        failure_class=payload.failure_class,
        error_summary=payload.error_summary,
        raw_snapshot=payload.raw_snapshot,
        broken_selector=payload.broken_selector,
        fixed_selector=payload.fixed_selector,
        test_pattern=payload.test_pattern,
        trigger_type=RepairTriggerType.MANUAL,
    )
    await session.commit()
    # Refresh to load relationships
    repo = RepairRepository(session)
    refreshed_run = await repo.get_run_by_id(run.id)
    return RepairRunResponse.model_validate(refreshed_run)


@router.post("/patches/{patch_id}/approve", response_model=RepairPatchResponse, summary="Approve and promote patch")
async def approve_and_promote_patch(
    patch_id: uuid.UUID,
    payload: PatchApproveRequest = PatchApproveRequest(),
    session: AsyncSession = Depends(get_db_session),
) -> RepairPatchResponse:
    """Approve a proposed patch and promote it to production connector code."""
    orchestrator = RepairOrchestrator(session)
    try:
        updated_patch = await orchestrator.promote_patch(patch_id, approved_by=payload.approved_by)
        await session.commit()
        return RepairPatchResponse.model_validate(updated_patch)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post("/patches/{patch_id}/reject", response_model=RepairPatchResponse, summary="Reject proposed patch")
async def reject_patch(
    patch_id: uuid.UUID,
    payload: PatchRejectRequest,
    session: AsyncSession = Depends(get_db_session),
) -> RepairPatchResponse:
    """Reject a proposed patch candidate."""
    repo = RepairRepository(session)
    patch = await repo.update_patch_state(
        patch_id=patch_id,
        state=RepairState.REJECTED,
        rejection_reason=payload.reason,
    )
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patch with id '{patch_id}' not found",
        )
    await repo.complete_run(patch.repair_run_id, outcome=RepairRunOutcome.REJECTED, error_summary=payload.reason)
    await session.commit()
    return RepairPatchResponse.model_validate(patch)


@router.post("/patches/{patch_id}/rollback", response_model=RepairPatchResponse, summary="Rollback promoted patch")
async def rollback_patch(
    patch_id: uuid.UUID,
    payload: PatchRollbackRequest = PatchRollbackRequest(),
    session: AsyncSession = Depends(get_db_session),
) -> RepairPatchResponse:
    """Roll back a promoted patch, restoring original connector version."""
    orchestrator = RepairOrchestrator(session)
    try:
        rolled_back = await orchestrator.rollback_patch(patch_id, reason=payload.reason)
        await session.commit()
        return RepairPatchResponse.model_validate(rolled_back)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
