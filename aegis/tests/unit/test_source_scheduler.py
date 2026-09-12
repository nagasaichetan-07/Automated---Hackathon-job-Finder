"""
Aegis — Unit & Integration Tests: Source Registry, Scheduler & Autonomous Ingestion

Validates:
1. Autonomous collection execution and opportunity ingestion.
2. Raw snapshot and opportunity idempotency (re-runs do not create duplicate snapshots).
3. Health state transitions: HEALTHY -> DEGRADED -> BROKEN and recovery.
4. Retry and backoff behavior on transient connector errors.
5. Source Registry CRUD REST API endpoints.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from apps.api.main import create_app
from apps.worker.tasks import collect_source_task, execute_source_collection
from connectors.base import TransientConnectorError
from connectors.greenhouse.connector import GreenhouseConnector
from core.schemas.domain import SourceHealth
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from storage.database import get_db_session
from storage.models.base import Base
from storage.models.opportunity import Opportunity
from storage.models.raw_snapshot import RawSnapshot
from storage.models.source_run import SourceRun
from storage.repositories.source_repository import SourceRepository

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def greenhouse_payload() -> str:
    path = FIXTURES_DIR / "greenhouse_jobs_fixture.json"
    return path.read_text(encoding="utf-8")


@pytest.fixture
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Ingestion & Idempotency Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_autonomous_collection_and_idempotency(
    db_session: AsyncSession,
    greenhouse_payload: str,
) -> None:
    """
    Demonstrates:
    1. First run creates RawSnapshot and persists normalized opportunities.
    2. Second run on identical content detects hash match and skips duplicate snapshot creation.
    """
    source = await SourceRepository.create_source(
        db_session,
        name="Acme Greenhouse",
        source_type="api",
        url="https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        connector_class="greenhouse",
        connector_config={"board_token": "acme"},
    )
    await db_session.commit()

    connector = GreenhouseConnector()

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = httpx.Response(
            status_code=200,
            text=greenhouse_payload,
            request=httpx.Request("GET", "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"),
        )

        # 1. First collection run
        result_1 = await execute_source_collection(
            db_session,
            source.id,
            connector_override=connector,
        )

        assert result_1["status"] == "success"
        assert result_1["records_collected"] == 2

        # Verify DB state after run 1
        snap_count_1 = await db_session.scalar(select(func.count(RawSnapshot.id)))
        opp_count_1 = await db_session.scalar(select(func.count(Opportunity.id)))
        assert snap_count_1 == 1
        assert opp_count_1 == 2

        # 2. Second collection run on identical payload (idempotency check)
        result_2 = await execute_source_collection(
            db_session,
            source.id,
            connector_override=connector,
        )

        assert result_2["status"] == "unchanged"
        assert result_2["records_collected"] == 0

        # Verify NO duplicate snapshots or opportunities created
        snap_count_2 = await db_session.scalar(select(func.count(RawSnapshot.id)))
        opp_count_2 = await db_session.scalar(select(func.count(Opportunity.id)))
        assert snap_count_2 == 1  # Still exactly 1
        assert opp_count_2 == 2   # Still exactly 2

        # Run metrics recorded both executions
        runs_count = await db_session.scalar(select(func.count(SourceRun.id)))
        assert runs_count == 2


# ---------------------------------------------------------------------------
# Health State Machine Transition Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_state_transitions(db_session: AsyncSession) -> None:
    """
    Validates health state machine:
    - Success -> HEALTHY
    - 1st failure -> DEGRADED
    - 2nd failure -> DEGRADED
    - 3rd failure -> BROKEN
    - Subsequent success -> Recovers to HEALTHY
    """
    source = await SourceRepository.create_source(
        db_session,
        name="Health Test Source",
        source_type="api",
        url="https://example.com/api",
        connector_class="greenhouse",
    )
    assert source.health_state == SourceHealth.HEALTHY.value

    # 1st failure -> DEGRADED
    await SourceRepository.record_run_outcome(db_session, source.id, success=False)
    assert source.consecutive_failures == 1
    assert source.health_state == SourceHealth.DEGRADED.value

    # 2nd failure -> still DEGRADED
    await SourceRepository.record_run_outcome(db_session, source.id, success=False)
    assert source.consecutive_failures == 2
    assert source.health_state == SourceHealth.DEGRADED.value

    # 3rd failure -> transitions to BROKEN
    await SourceRepository.record_run_outcome(db_session, source.id, success=False)
    assert source.consecutive_failures == 3
    assert source.health_state == SourceHealth.BROKEN.value

    # Recovery: 1 success -> resets to HEALTHY
    await SourceRepository.record_run_outcome(db_session, source.id, success=True)
    assert source.consecutive_failures == 0
    assert source.health_state == SourceHealth.HEALTHY.value


# ---------------------------------------------------------------------------
# Retry and Backoff Handling Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transient_error_triggers_retry_exception(
    db_session: AsyncSession,
) -> None:
    """
    Network timeouts or connection drops raise TransientConnectorError,
    signaling Celery's autoretry_for backoff policy.
    """
    source = await SourceRepository.create_source(
        db_session,
        name="Flaky Source",
        source_type="api",
        url="https://flaky.example.com",
        connector_class="greenhouse",
        connector_config={"board_token": "flaky"},
    )
    await db_session.commit()

    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")):
        with pytest.raises(TransientConnectorError, match="Transient network failure"):
            await execute_source_collection(db_session, source.id)

    # Health state was marked degraded and run was logged
    await db_session.refresh(source)
    assert source.consecutive_failures == 1
    assert source.health_state == SourceHealth.DEGRADED.value


def test_celery_task_retry_configuration() -> None:
    """Verify Celery task has correct retry policy configured."""
    assert TransientConnectorError in collect_source_task.autoretry_for
    assert collect_source_task.retry_backoff is True
    assert collect_source_task.max_retries == 3


# ---------------------------------------------------------------------------
# Source Registry REST API Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_api_crud_endpoints(db_session: AsyncSession) -> None:
    """Validate REST API for source CRUD and health probing."""
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create source
        create_resp = await client.post(
            "/api/v1/sources",
            json={
                "name": "GitHub Greenhouse Board",
                "source_type": "api",
                "url": "https://boards-api.greenhouse.io/v1/boards/github/jobs",
                "connector_class": "greenhouse",
                "connector_config": {"board_token": "github"},
                "cadence": "0 */4 * * *",
                "enabled": True,
            },
        )
        assert create_resp.status_code == 201
        source_data = create_resp.json()
        source_id = source_data["id"]
        assert source_data["name"] == "GitHub Greenhouse Board"
        assert source_data["health_state"] == SourceHealth.HEALTHY.value

        # 2. List sources
        list_resp = await client.get("/api/v1/sources")
        assert list_resp.status_code == 200
        sources = list_resp.json()
        assert len(sources) >= 1

        # 3. Get source details with run audit
        detail_resp = await client.get(f"/api/v1/sources/{source_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["id"] == source_id
        assert "recent_runs" in detail

        # 4. Patch source
        patch_resp = await client.patch(
            f"/api/v1/sources/{source_id}",
            json={"cadence": "0 */12 * * *", "enabled": False},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["cadence"] == "0 */12 * * *"
        assert patch_resp.json()["enabled"] is False

        # 5. Delete source
        del_resp = await client.delete(f"/api/v1/sources/{source_id}")
        assert del_resp.status_code == 204

        # 6. Verify 404
        get_again = await client.get(f"/api/v1/sources/{source_id}")
        assert get_again.status_code == 404
