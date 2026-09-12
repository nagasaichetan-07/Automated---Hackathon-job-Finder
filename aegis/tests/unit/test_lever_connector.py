"""
Aegis — Unit Tests: Lever Postings API Connector

Tests fetch parsing, schema conformance, workplaceType mapping,
and health checks using recorded offline fixtures.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from connectors.lever.connector import LeverConnector
from core.schemas.domain import OpportunityCategory, OpportunityMode, OpportunitySchema

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def lever_fixture_text() -> str:
    path = FIXTURES_DIR / "lever_postings_fixture.json"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def lever_connector() -> LeverConnector:
    return LeverConnector()


@pytest.mark.asyncio
async def test_lever_fetch_parses_fixture(
    lever_connector: LeverConnector,
    lever_fixture_text: str,
) -> None:
    """Connector fetch parses JSON array and computes content hash."""
    config = {"site": "apex"}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = httpx.Response(
            status_code=200,
            text=lever_fixture_text,
            request=httpx.Request("GET", "https://api.lever.co/v0/postings/apex?mode=json"),
        )

        fetch_result = await lever_connector.fetch(config)

        assert fetch_result.record_count == 2
        assert len(fetch_result.records) == 2
        assert len(fetch_result.content_hash) == 64
        assert fetch_result.records[0]["id"] == "e4f3a71b-7a89-4bc2-8cd3-123456789abc"


def test_lever_normalize_internship(
    lever_connector: LeverConnector,
    lever_fixture_text: str,
) -> None:
    """Internship posting is normalized as INTERNSHIP with hybrid mode."""
    postings = json.loads(lever_fixture_text)
    raw_item = postings[0]
    source_id = uuid.uuid4()

    opp = lever_connector.normalize_raw(raw_item, source_id)

    assert isinstance(opp, OpportunitySchema)
    assert opp.source_id == source_id
    assert opp.external_id == "e4f3a71b-7a89-4bc2-8cd3-123456789abc"
    assert opp.title == "Data Science & AI Intern"
    assert opp.category == OpportunityCategory.INTERNSHIP
    assert opp.mode == OpportunityMode.HYBRID
    assert opp.location == "New York, NY"
    assert opp.url == "https://jobs.lever.co/apex/e4f3a71b-7a89-4bc2-8cd3-123456789abc"
    assert "Data Intelligence" in opp.skills_themes
    assert "title" in opp.evidence
    assert opp.published_at is not None


def test_lever_normalize_remote_job(
    lever_connector: LeverConnector,
    lever_fixture_text: str,
) -> None:
    """Full time job with workplaceType=remote is normalized as JOB with remote mode."""
    postings = json.loads(lever_fixture_text)
    raw_item = postings[1]
    source_id = uuid.uuid4()

    opp = lever_connector.normalize_raw(raw_item, source_id)

    assert isinstance(opp, OpportunitySchema)
    assert opp.category == OpportunityCategory.JOB
    assert opp.mode == OpportunityMode.REMOTE
    assert opp.location == "Austin, TX"
    assert opp.title == "Full Stack Platform Engineer"


def test_lever_missing_site(lever_connector: LeverConnector) -> None:
    """Omitting site raises ValueError."""
    with pytest.raises(ValueError, match="site"):
        lever_connector._get_site_url({})


@pytest.mark.asyncio
async def test_lever_health_check_healthy(
    lever_connector: LeverConnector,
    lever_fixture_text: str,
) -> None:
    """Health check reports healthy with count when 200 OK."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = httpx.Response(
            status_code=200,
            text=lever_fixture_text,
            request=httpx.Request("GET", "https://api.lever.co/v0/postings/apex?mode=json"),
        )
        health = await lever_connector.health_check({"site": "apex"})
        assert health.healthy is True
        assert health.status_code == 200
        assert health.message is not None
        assert "2 active postings" in health.message
