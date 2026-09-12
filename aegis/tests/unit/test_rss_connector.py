"""
Aegis — Unit Tests: RSS & Atom Connector

Tests RSS 2.0 and Atom 1.0 feed parsing, XML safety defenses,
schema normalization, and pubDate handling.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from connectors.rss.connector import RSSConnector, _safe_parse_xml
from core.schemas.domain import OpportunityCategory, OpportunityMode, OpportunitySchema

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def rss_fixture_text() -> str:
    path = FIXTURES_DIR / "sample_rss_feed.xml"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def atom_fixture_text() -> str:
    path = FIXTURES_DIR / "sample_atom_feed.xml"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def rss_connector() -> RSSConnector:
    return RSSConnector()


@pytest.mark.asyncio
async def test_rss_fetch_parses_feed(
    rss_connector: RSSConnector,
    rss_fixture_text: str,
) -> None:
    """RSS fetch parses items and calculates SHA256 content hash."""
    config = {"feed_url": "https://example.org/opportunities.xml"}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = httpx.Response(
            status_code=200,
            text=rss_fixture_text,
            request=httpx.Request("GET", "https://example.org/opportunities.xml"),
        )

        fetch_result = await rss_connector.fetch(config)

        assert fetch_result.record_count == 2
        assert len(fetch_result.records) == 2
        assert len(fetch_result.content_hash) == 64
        assert "Hackathon" in fetch_result.records[0]["title"]


@pytest.mark.asyncio
async def test_atom_fetch_parses_entries(
    rss_connector: RSSConnector,
    atom_fixture_text: str,
) -> None:
    """Atom fetch parses entries with namespace handling."""
    config = {"feed_url": "https://example.com/atom.xml"}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = httpx.Response(
            status_code=200,
            text=atom_fixture_text,
            request=httpx.Request("GET", "https://example.com/atom.xml"),
        )

        fetch_result = await rss_connector.fetch(config)

        assert fetch_result.record_count == 1
        assert "Quantum" in fetch_result.records[0]["title"]
        assert fetch_result.records[0]["link"] == "https://example.com/fellowships/quantum-2026"


def test_rss_normalize_hackathon(
    rss_connector: RSSConnector,
    rss_fixture_text: str,
) -> None:
    """Feed entry with 'hackathon' in title/categories normalizes as HACKATHON category."""
    root = _safe_parse_xml(rss_fixture_text)
    items = rss_connector._extract_items_from_xml(root)
    raw_hackathon = items[0]
    source_id = uuid.uuid4()

    opp = rss_connector.normalize_raw(raw_hackathon, source_id)

    assert isinstance(opp, OpportunitySchema)
    assert opp.category == OpportunityCategory.HACKATHON
    assert opp.mode == OpportunityMode.REMOTE
    assert opp.url == "https://example.org/hackathons/global-ai-2026"
    assert "Hackathon" in opp.skills_themes


def test_rss_normalize_internship(
    rss_connector: RSSConnector,
    rss_fixture_text: str,
) -> None:
    """Feed entry with 'internship' normalizes as INTERNSHIP."""
    root = _safe_parse_xml(rss_fixture_text)
    items = rss_connector._extract_items_from_xml(root)
    raw_internship = items[1]
    source_id = uuid.uuid4()

    opp = rss_connector.normalize_raw(raw_internship, source_id)

    assert isinstance(opp, OpportunitySchema)
    assert opp.category == OpportunityCategory.INTERNSHIP
    assert opp.published_at is not None


def test_xml_entity_expansion_defense() -> None:
    """XML with DOCTYPE ENTITY expansion payload is rejected."""
    hostile_xml = """<?xml version="1.0"?>
    <!DOCTYPE lolz [
     <!ENTITY lol "lol">
     <!ELEMENT lolz (#PCDATA)>
     <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
    ]>
    <lolz>&lol1;</lolz>
    """
    with pytest.raises(ValueError, match="Entity Expansion"):
        _safe_parse_xml(hostile_xml)
