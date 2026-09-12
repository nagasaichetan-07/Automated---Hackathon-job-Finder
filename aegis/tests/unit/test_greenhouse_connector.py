"""
Aegis — Unit Tests: Greenhouse Job Board Connector

Tests fetch parsing, schema conformance, category and mode heuristics,
and health checks using recorded offline fixtures.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from connectors.greenhouse.connector import GreenhouseConnector
from core.schemas.domain import OpportunityCategory, OpportunityMode, OpportunitySchema

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def greenhouse_fixture_text() -> str:
    path = FIXTURES_DIR / "greenhouse_jobs_fixture.json"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def greenhouse_connector() -> GreenhouseConnector:
    return GreenhouseConnector()


@pytest.mark.asyncio
async def test_greenhouse_fetch_parses_fixture(
    greenhouse_connector: GreenhouseConnector,
    greenhouse_fixture_text: str,
) -> None:
    """Connector fetch parses JSON payload and computes SHA256 content hash."""
    config = {"board_token": "acme"}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = httpx.Response(
            status_code=200,
            text=greenhouse_fixture_text,
            request=httpx.Request("GET", "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"),
        )
        mock_get.return_value = mock_response

        fetch_result = await greenhouse_connector.fetch(config)

        assert fetch_result.record_count == 2
        assert len(fetch_result.records) == 2
        assert len(fetch_result.content_hash) == 64
        assert fetch_result.records[0]["id"] == 4120938002


def test_greenhouse_normalize_internship(
    greenhouse_connector: GreenhouseConnector,
    greenhouse_fixture_text: str,
) -> None:
    """Job with 'intern' in title is normalized as INTERNSHIP with hybrid mode."""
    data = json.loads(greenhouse_fixture_text)
    raw_job = data["jobs"][0]
    source_id = uuid.uuid4()

    opp = greenhouse_connector.normalize_raw(raw_job, source_id)

    assert isinstance(opp, OpportunitySchema)
    assert opp.source_id == source_id
    assert opp.external_id == "4120938002"
    assert "Intern" in opp.title
    assert opp.category == OpportunityCategory.INTERNSHIP
    assert opp.mode == OpportunityMode.HYBRID
    assert opp.location == "San Francisco, CA (Hybrid)"
    assert opp.url == "https://boards.greenhouse.io/acme/jobs/4120938002"
    assert "Cloud Infrastructure" in opp.skills_themes
    assert "title" in opp.evidence
    assert opp.content_hash is not None


def test_greenhouse_normalize_job(
    greenhouse_connector: GreenhouseConnector,
    greenhouse_fixture_text: str,
) -> None:
    """Full time job without intern keywords is normalized as JOB with remote mode."""
    data = json.loads(greenhouse_fixture_text)
    raw_job = data["jobs"][1]
    source_id = uuid.uuid4()

    opp = greenhouse_connector.normalize_raw(raw_job, source_id)

    assert isinstance(opp, OpportunitySchema)
    assert opp.category == OpportunityCategory.JOB
    assert opp.mode == OpportunityMode.REMOTE
    assert opp.location == "Remote, US"
    assert "Machine Learning" in opp.title


def test_greenhouse_missing_board_token(
    greenhouse_connector: GreenhouseConnector,
) -> None:
    """Omitting board_token raises ValueError."""
    with pytest.raises(ValueError, match="board_token"):
        greenhouse_connector._get_board_url({})


@pytest.mark.asyncio
async def test_greenhouse_health_check_healthy(
    greenhouse_connector: GreenhouseConnector,
    greenhouse_fixture_text: str,
) -> None:
    """Health check reports healthy with job count when 200 OK."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = httpx.Response(
            status_code=200,
            text=greenhouse_fixture_text,
            request=httpx.Request("GET", "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"),
        )
        health = await greenhouse_connector.health_check({"board_token": "acme"})
        assert health.healthy is True
        assert health.status_code == 200
        assert health.message is not None
        assert "2 active jobs" in health.message


@pytest.mark.asyncio
async def test_greenhouse_health_check_error(
    greenhouse_connector: GreenhouseConnector,
) -> None:
    """Health check reports unhealthy when HTTP 404."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = httpx.Response(
            status_code=404,
            text='{"error":"Not Found"}',
            request=httpx.Request("GET", "https://boards-api.greenhouse.io/v1/boards/invalid/jobs?content=true"),
        )
        health = await greenhouse_connector.health_check({"board_token": "invalid"})
        assert health.healthy is False
        assert health.status_code == 404
