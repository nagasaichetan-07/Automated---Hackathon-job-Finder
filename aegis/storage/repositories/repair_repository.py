"""
Aegis — Repair Repository

Provides database access and lifecycle management for RepairRun and RepairPatch entities.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.schemas.domain import FailureClass, RepairRunOutcome, RepairState, RepairTriggerType
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from storage.models.repair import RepairPatch, RepairRun


class RepairRepository:
    """Repository for self-healing repair runs and patches."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(
        self,
        source_id: uuid.UUID,
        failure_class: FailureClass | str = FailureClass.SELECTOR_NOT_FOUND,
        trigger_type: RepairTriggerType | str = RepairTriggerType.AUTOMATIC,
        error_summary: str | None = None,
        diagnosis: dict[str, Any] | None = None,
    ) -> RepairRun:
        """Create a new repair run record."""
        failure_val = failure_class.value if isinstance(failure_class, FailureClass) else failure_class
        trigger_val = trigger_type.value if isinstance(trigger_type, RepairTriggerType) else trigger_type

        run = RepairRun(
            source_id=source_id,
            failure_class=failure_val,
            trigger_type=trigger_val,
            error_summary=error_summary,
            diagnosis=diagnosis or {},
            started_at=datetime.now(UTC),
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_run_by_id(self, run_id: uuid.UUID) -> RepairRun | None:
        """Fetch a repair run by ID with eager loading of patches."""
        stmt = (
            select(RepairRun)
            .options(selectinload(RepairRun.patches))
            .where(RepairRun.id == run_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        source_id: uuid.UUID | None = None,
        outcome: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RepairRun]:
        """List repair runs ordered by started_at descending."""
        stmt = select(RepairRun).options(selectinload(RepairRun.patches))
        if source_id:
            stmt = stmt.where(RepairRun.source_id == source_id)
        if outcome:
            stmt = stmt.where(RepairRun.outcome == outcome)

        stmt = stmt.order_by(desc(RepairRun.started_at)).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def complete_run(
        self,
        run_id: uuid.UUID,
        outcome: RepairRunOutcome | str,
        error_summary: str | None = None,
        diagnosis: dict[str, Any] | None = None,
    ) -> RepairRun | None:
        """Complete a repair run recording its outcome and completion timestamp."""
        run = await self.get_run_by_id(run_id)
        if not run:
            return None

        outcome_val = outcome.value if isinstance(outcome, RepairRunOutcome) else outcome
        run.outcome = outcome_val
        run.completed_at = datetime.now(UTC)
        if error_summary:
            run.error_summary = error_summary
        if diagnosis:
            run.diagnosis = {**run.diagnosis, **diagnosis}
        return run

    async def create_patch(
        self,
        repair_run_id: uuid.UUID,
        target_file: str,
        diff_content: str,
        connector_version_before: str | None = None,
        state: RepairState | str = RepairState.PROPOSED,
    ) -> RepairPatch:
        """Create a new proposed patch for a repair run."""
        state_val = state.value if isinstance(state, RepairState) else state

        patch = RepairPatch(
            repair_run_id=repair_run_id,
            target_file=target_file,
            diff_content=diff_content,
            connector_version_before=connector_version_before,
            state=state_val,
            proposed_at=datetime.now(UTC),
        )
        self.session.add(patch)
        await self.session.flush()
        return patch

    async def get_patch_by_id(self, patch_id: uuid.UUID) -> RepairPatch | None:
        """Fetch a repair patch by ID."""
        stmt = select(RepairPatch).where(RepairPatch.id == patch_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_patch_state(
        self,
        patch_id: uuid.UUID,
        state: RepairState | str,
        sandbox_passed: bool | None = None,
        test_results: dict[str, Any] | None = None,
        validation_results: dict[str, Any] | None = None,
        approved_by: str | None = None,
        connector_version_after: str | None = None,
        rejection_reason: str | None = None,
        promoted_at: datetime | None = None,
        rolled_back_at: datetime | None = None,
    ) -> RepairPatch | None:
        """Update the state and metadata of a repair patch."""
        patch = await self.get_patch_by_id(patch_id)
        if not patch:
            return None

        state_val = state.value if isinstance(state, RepairState) else state
        patch.state = state_val
        now = datetime.now(UTC)

        if sandbox_passed is not None:
            patch.sandbox_passed = sandbox_passed
            patch.tested_at = now
        if test_results is not None:
            patch.test_results = test_results
        if validation_results is not None:
            patch.validation_results = validation_results
        if approved_by is not None:
            patch.approved_by = approved_by
        if connector_version_after is not None:
            patch.connector_version_after = connector_version_after
        if rejection_reason is not None:
            patch.rejection_reason = rejection_reason
        if promoted_at is not None or state_val == RepairState.PROMOTED.value:
            patch.promoted_at = promoted_at or now
        if rolled_back_at is not None:
            patch.rolled_back_at = rolled_back_at

        return patch
