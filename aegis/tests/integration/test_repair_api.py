"""
Aegis — Integration Tests for Self-Healing Repair API Router
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apps.api.main import app
from httpx import ASGITransport, AsyncClient
from storage.database import get_db_session

MOCK_SOURCE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MOCK_RUN_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
MOCK_PATCH_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _mock_repair_patch():
    patch_obj = MagicMock()
    patch_obj.id = MOCK_PATCH_ID
    patch_obj.repair_run_id = MOCK_RUN_ID
    patch_obj.state = "TESTED"
    patch_obj.target_file = "connectors/web/demo.py"
    patch_obj.diff_content = "--- a/demo.py\n+++ b/demo.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n"
    patch_obj.sandbox_passed = True
    patch_obj.test_results = {"exit_code": 0, "success": True}
    patch_obj.validation_results = {"is_valid": True, "passed_checks": ["all"]}
    patch_obj.approved_by = None
    patch_obj.connector_version_before = "x = 1\n"
    patch_obj.connector_version_after = "x = 2\n"
    patch_obj.rejection_reason = None
    patch_obj.proposed_at = datetime.now(UTC)
    patch_obj.tested_at = datetime.now(UTC)
    patch_obj.promoted_at = None
    patch_obj.rolled_back_at = None
    return patch_obj


def _mock_repair_run():
    run_obj = MagicMock()
    run_obj.id = MOCK_RUN_ID
    run_obj.source_id = MOCK_SOURCE_ID
    run_obj.trigger_type = "automatic"
    run_obj.failure_class = "selector_not_found"
    run_obj.error_summary = "Selector missing"
    run_obj.diagnosis = {}
    run_obj.outcome = "pending"
    run_obj.started_at = datetime.now(UTC)
    run_obj.completed_at = None
    run_obj.patches = [_mock_repair_patch()]
    return run_obj


async def _override_get_db():
    session = AsyncMock()
    yield session


app.dependency_overrides[get_db_session] = _override_get_db


class TestRepairAPIEndpoints:
    """Integration test suite for self-healing repair endpoints."""

    @pytest.mark.asyncio
    async def test_list_repair_runs(self) -> None:
        with patch("apps.api.routers.repair.RepairRepository") as MockRepo:
            MockRepo.return_value.list_runs = AsyncMock(return_value=[_mock_repair_run()])

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get("/api/v1/repair/runs")
                assert res.status_code == 200
                data = res.json()
                assert isinstance(data, list)
                assert len(data) == 1
                assert data[0]["id"] == str(MOCK_RUN_ID)

    @pytest.mark.asyncio
    async def test_get_repair_run_details(self) -> None:
        with patch("apps.api.routers.repair.RepairRepository") as MockRepo:
            MockRepo.return_value.get_run_by_id = AsyncMock(return_value=_mock_repair_run())

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get(f"/api/v1/repair/runs/{MOCK_RUN_ID}")
                assert res.status_code == 200
                data = res.json()
                assert data["failure_class"] == "selector_not_found"
                assert len(data["patches"]) == 1

    @pytest.mark.asyncio
    async def test_approve_and_promote_patch(self) -> None:
        with patch("apps.api.routers.repair.RepairOrchestrator") as MockOrchestrator:
            promoted_patch = _mock_repair_patch()
            promoted_patch.state = "PROMOTED"
            promoted_patch.approved_by = "admin_test"
            MockOrchestrator.return_value.promote_patch = AsyncMock(return_value=promoted_patch)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/repair/patches/{MOCK_PATCH_ID}/approve",
                    json={"approved_by": "admin_test"},
                )
                assert res.status_code == 200
                data = res.json()
                assert data["state"] == "PROMOTED"
                assert data["approved_by"] == "admin_test"

    @pytest.mark.asyncio
    async def test_rollback_patch(self) -> None:
        with patch("apps.api.routers.repair.RepairOrchestrator") as MockOrchestrator:
            rolled_back_patch = _mock_repair_patch()
            rolled_back_patch.state = "REJECTED"
            rolled_back_patch.rejection_reason = "Rolled back: Manual test"
            MockOrchestrator.return_value.rollback_patch = AsyncMock(return_value=rolled_back_patch)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/repair/patches/{MOCK_PATCH_ID}/rollback",
                    json={"reason": "Manual test"},
                )
                assert res.status_code == 200
                data = res.json()
                assert data["state"] == "REJECTED"
