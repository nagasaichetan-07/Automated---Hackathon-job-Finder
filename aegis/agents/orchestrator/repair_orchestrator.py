"""
Aegis — Repair Orchestrator

Coordinates the autonomous self-healing pipeline across anomaly detection,
isolated sandboxed testing, security validation, approval gating, promotion, and rollback.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.orchestrator.anomaly_detector import AnomalyDetector
from agents.orchestrator.failure_classifier import FailureClassifier
from agents.repair.repair_agent import RepairAgent
from agents.repair.sandbox import RepairSandbox
from agents.validation.patch_validator import PatchValidator
from core.schemas.domain import FailureClass, RepairRunOutcome, RepairState, RepairTriggerType
from sqlalchemy.ext.asyncio import AsyncSession
from storage.models.repair import RepairPatch, RepairRun
from storage.repositories.repair_repository import RepairRepository


class RepairOrchestrator:
    """Orchestrator managing self-healing repair runs, gates, promotion, and rollback."""

    def __init__(
        self,
        session: AsyncSession,
        root_dir: str | Path | None = None,
    ) -> None:
        self.session = session
        self.repository = RepairRepository(session)
        self.root_dir = Path(root_dir or os.getcwd()).resolve()

        self.anomaly_detector = AnomalyDetector()
        self.repair_agent = RepairAgent()
        self.sandbox = RepairSandbox(root_dir=self.root_dir)
        self.validator = PatchValidator()

    @property
    def is_repair_enabled(self) -> bool:
        """Emergency kill switch: AEGIS_REPAIR_ENABLED env var (default: True)."""
        val = os.getenv("AEGIS_REPAIR_ENABLED", "true").lower()
        return val in ("true", "1", "yes", "on")

    @property
    def auto_promote_enabled(self) -> bool:
        """Autonomous promotion flag: AEGIS_AUTO_PROMOTE_REPAIRS env var (default: False)."""
        val = os.getenv("AEGIS_AUTO_PROMOTE_REPAIRS", "false").lower()
        return val in ("true", "1", "yes", "on")

    async def execute_self_healing_run(
        self,
        source_id: uuid.UUID,
        target_file_rel: str,
        failure_class: FailureClass | str = FailureClass.SELECTOR_NOT_FOUND,
        error_summary: str | None = None,
        raw_snapshot: str | None = None,
        broken_selector: str | None = None,
        fixed_selector: str | None = None,
        test_pattern: str | None = None,
        trigger_type: RepairTriggerType | str = RepairTriggerType.AUTOMATIC,
    ) -> tuple[RepairRun, RepairPatch | None]:
        """
        Execute the full self-healing pipeline for a broken connector.
        """
        # 1. Check Kill Switch
        if not self.is_repair_enabled:
            run = await self.repository.create_run(
                source_id=source_id,
                failure_class=failure_class,
                trigger_type=trigger_type,
                error_summary="Self-healing disabled via kill switch (AEGIS_REPAIR_ENABLED=false)",
            )
            await self.repository.complete_run(run.id, outcome=RepairRunOutcome.REJECTED)
            return run, None

        # 2. Create Repair Run Audit Record
        run = await self.repository.create_run(
            source_id=source_id,
            failure_class=failure_class,
            trigger_type=trigger_type,
            error_summary=error_summary,
        )

        target_path = self.root_dir / target_file_rel
        if not target_path.exists():
            await self.repository.complete_run(
                run.id,
                outcome=RepairRunOutcome.FAILURE,
                error_summary=f"Target file not found: {target_file_rel}",
            )
            return run, None

        original_code = target_path.read_text(encoding="utf-8")

        # 3. Synthesize Minimal Patch
        sanitized_snapshot = self.repair_agent.sanitize_untrusted_content(raw_snapshot or "")
        diff_content = self.repair_agent.synthesize_fallback_patch(
            target_file_rel=target_file_rel,
            source_code=original_code,
            failure_class=failure_class,
            broken_selector=broken_selector,
            fixed_selector=fixed_selector,
        )

        patch = await self.repository.create_patch(
            repair_run_id=run.id,
            target_file=target_file_rel,
            diff_content=diff_content,
            connector_version_before=original_code,
            state=RepairState.PROPOSED,
        )

        # 4. Test inside Isolated Sandbox
        sandbox_res = self.sandbox.run_tests_in_sandbox(
            target_file_rel=target_file_rel,
            patch_diff=diff_content,
            test_pattern=test_pattern,
        )

        # 5. Security & Quality Validation
        patched_code = self.sandbox.apply_patch_to_file(
            target_path, diff_content
        ) if sandbox_res.success else original_code
        # Restore target path immediately if modified during helper call
        if patched_code != original_code:
            target_path.write_text(original_code, encoding="utf-8")

        val_res = self.validator.validate_patch(
            target_file_rel=target_file_rel,
            diff_content=diff_content,
            patched_full_code=patched_code,
        )

        test_info = {
            "exit_code": sandbox_res.exit_code,
            "success": sandbox_res.success,
            "stdout": sandbox_res.stdout[:2000],
            "stderr": sandbox_res.stderr[:2000],
        }

        val_info = {
            "is_valid": val_res.is_valid,
            "passed_checks": val_res.checks_passed,
            "failures": val_res.failures,
        }

        # 6. Evaluate Gate
        if sandbox_res.success and val_res.is_valid:
            patch = await self.repository.update_patch_state(
                patch_id=patch.id,
                state=RepairState.TESTED,
                sandbox_passed=True,
                test_results=test_info,
                validation_results=val_info,
            )

            # Auto-promote if flag enabled
            if self.auto_promote_enabled and patch is not None:
                patch = await self.promote_patch(patch.id, approved_by="autonomous")
        else:
            rejection_reason = f"Sandbox success: {sandbox_res.success}, Validation valid: {val_res.is_valid}"
            if patch is not None:
                patch = await self.repository.update_patch_state(
                    patch_id=patch.id,
                    state=RepairState.REJECTED,
                    sandbox_passed=sandbox_res.success,
                    test_results=test_info,
                    validation_results=val_info,
                    rejection_reason=rejection_reason,
                )
            await self.repository.complete_run(
                run.id,
                outcome=RepairRunOutcome.FAILURE,
                error_summary=rejection_reason,
            )

        return run, patch

    async def promote_patch(
        self,
        patch_id: uuid.UUID,
        approved_by: str = "human_admin",
    ) -> RepairPatch:
        """
        Promote an approved repair patch to production code.
        Modifies target connector file and logs completion.
        """
        patch = await self.repository.get_patch_by_id(patch_id)
        if not patch:
            raise ValueError(f"RepairPatch not found: {patch_id}")

        target_path = self.root_dir / patch.target_file
        if not target_path.exists():
            raise FileNotFoundError(f"Target file missing for promotion: {patch.target_file}")

        # Store backup version if not set
        if not patch.connector_version_before:
            patch.connector_version_before = target_path.read_text(encoding="utf-8")

        # Apply diff to target file in production working directory
        new_content = self.sandbox.apply_patch_to_file(target_path, patch.diff_content)

        updated_patch = await self.repository.update_patch_state(
            patch_id=patch.id,
            state=RepairState.PROMOTED,
            approved_by=approved_by,
            connector_version_after=new_content,
            promoted_at=datetime.now(UTC),
        )

        if not updated_patch:
            raise RuntimeError(f"Failed to update patch state for {patch_id}")

        # Complete associated repair run
        await self.repository.complete_run(
            run_id=patch.repair_run_id,
            outcome=RepairRunOutcome.SUCCESS,
        )

        return updated_patch

    async def rollback_patch(
        self,
        patch_id: uuid.UUID,
        reason: str = "Manual rollback triggered",
    ) -> RepairPatch:
        """
        Roll back a promoted patch, restoring original connector version.
        """
        patch = await self.repository.get_patch_by_id(patch_id)
        if not patch:
            raise ValueError(f"RepairPatch not found: {patch_id}")

        if not patch.connector_version_before:
            raise ValueError("Cannot rollback patch: missing connector_version_before backup")

        target_path = self.root_dir / patch.target_file
        target_path.write_text(patch.connector_version_before, encoding="utf-8")

        updated_patch = await self.repository.update_patch_state(
            patch_id=patch.id,
            state=RepairState.REJECTED,
            rejection_reason=f"Rolled back: {reason}",
            rolled_back_at=datetime.now(UTC),
        )

        if not updated_patch:
            raise RuntimeError(f"Failed to update patch state for {patch_id}")

        await self.repository.complete_run(
            run_id=patch.repair_run_id,
            outcome=RepairRunOutcome.ROLLED_BACK,
            error_summary=f"Rolled back: {reason}",
        )

        return updated_patch

