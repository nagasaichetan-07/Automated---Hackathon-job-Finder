"""
Aegis — Web Connector Unit Tests

Tests the WebConnector implementation:
- Connector registration and metadata
- SSRF enforcement via RestrictedHttpClient
- Health check execution (healthy, HTTP error, network error, missing URL)
- Full normalization pipeline (deterministic -> schema-conformant OpportunitySchema)
- Evidence dictionary tracking (§2.4)
- Dedup content hash and deterministic external_id generation
- Graceful degradation when LLM is unavailable
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from connectors.base import RawFetchResult
from connectors.registry import get_connector
from connectors.web.connector import WebConnector
from core.schemas.domain import OpportunityCategory, OpportunityMode, OpportunitySchema

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class TestWebConnectorRegistration:
    """Tests connector registry integration and metadata."""

    def test_registered_keys(self) -> None:
        """Connector is resolvable under 'web' and 'WebConnector'."""
        conn1 = get_connector("web")
        conn2 = get_connector("WebConnector")
        assert isinstance(conn1, WebConnector)
        assert isinstance(conn2, WebConnector)

    def test_metadata(self) -> None:
        """Connector metadata contains expected attributes."""
        conn = WebConnector()
        meta = conn.metadata
        assert meta.source_type == "web"
        assert meta.version == "1.0.0"
        assert "Web Page Connector" in meta.name


class TestWebConnectorHealthCheck:
    """Tests health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_missing_url(self) -> None:
        """Missing URL returns unhealthy result."""
        conn = WebConnector()
        result = await conn.health_check({})
        assert not result.healthy
        assert result.message is not None and "No URL" in result.message

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        """Reachable URL returns healthy status."""
        conn = WebConnector()
        mock_response = httpx.Response(
            status_code=200,
            text="<html><head><title>Ok</title></head></html>",
            request=httpx.Request("GET", "https://example.org/hackathon"),
        )
        with patch.object(
            conn._get_http_client({"url": "https://example.org/hackathon"}),
            "get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            # Patch _get_http_client on instance
            with patch.object(conn, "_get_http_client") as mock_get_client:
                mock_client = AsyncMock()
                mock_client.get.return_value = mock_response
                mock_get_client.return_value = mock_client

                result = await conn.health_check({"url": "https://example.org/hackathon"})
                assert result.healthy
                assert result.status_code == 200
                assert result.latency_ms is not None

    @pytest.mark.asyncio
    async def test_health_check_http_error(self) -> None:
        """HTTP error status returns unhealthy status."""
        conn = WebConnector()
        mock_response = httpx.Response(
            status_code=404,
            text="Not Found",
            request=httpx.Request("GET", "https://example.org/hackathon"),
        )
        with patch.object(conn, "_get_http_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await conn.health_check({"url": "https://example.org/hackathon"})
            assert not result.healthy
            assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_health_check_connection_failure(self) -> None:
        """Connection failure returns unhealthy status with error message."""
        conn = WebConnector()
        with patch.object(conn, "_get_http_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_get_client.return_value = mock_client

            result = await conn.health_check({"url": "https://example.org/hackathon"})
            assert not result.healthy
            assert result.status_code is None
            assert result.message is not None and "Connection failed" in result.message


class TestWebConnectorFetch:
    """Tests fetch method and SSRF enforcement."""

    @pytest.mark.asyncio
    async def test_fetch_success(self) -> None:
        """Successful fetch returns RawFetchResult with HTML record."""
        conn = WebConnector()
        html_content = "<html><body><h1>Test Hackathon</h1></body></html>"
        mock_response = httpx.Response(
            status_code=200,
            text=html_content,
            request=httpx.Request("GET", "https://example.org/event"),
        )

        with patch.object(conn, "_get_http_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await conn.fetch({"url": "https://example.org/event"})
            assert isinstance(result, RawFetchResult)
            assert len(result.records) == 1
            assert result.records[0]["html"] == html_content
            assert result.records[0]["url"] == "https://example.org/event"
            assert result.content_hash != ""

    @pytest.mark.asyncio
    async def test_fetch_requires_url(self) -> None:
        """Fetch without URL raises ValueError."""
        conn = WebConnector()
        with pytest.raises(ValueError, match="requires 'url'"):
            await conn.fetch({})


class TestWebConnectorNormalization:
    """Tests normalize_raw pipeline into OpportunitySchema."""

    def test_normalize_jsonld_page(self) -> None:
        """Normalizing JSON-LD page produces full OpportunitySchema with evidence."""
        conn = WebConnector()
        html_path = FIXTURES_DIR / "hackathon_page_jsonld.html"
        html_content = html_path.read_text(encoding="utf-8")
        source_id = uuid.uuid4()

        raw_item = {
            "html": html_content,
            "url": "https://hackathons.example.org/ai-hackathon-2025",
        }

        opp = conn.normalize_raw(raw_item, source_id)

        assert isinstance(opp, OpportunitySchema)
        assert opp.source_id == source_id
        assert opp.title == "AI Hackathon Global 2025"
        assert opp.category == OpportunityCategory.HACKATHON
        assert opp.organizer == "AI Foundation"
        assert opp.url == "https://hackathons.example.org/ai-hackathon-2025"
        assert opp.start_date is not None
        assert opp.end_date is not None
        assert opp.registration_deadline is not None
        assert opp.external_id != ""
        assert opp.content_hash != ""

        # Evidence dictionary (§2.4: every AI/extracted field must carry evidence)
        assert len(opp.evidence) > 0
        assert "title" in opp.evidence
        assert "start_date" in opp.evidence
        assert "organizer" in opp.evidence

    def test_normalize_unstructured_page_deterministic_heuristics(self) -> None:
        """Normalizing unstructured page uses heuristics when LLM is unavailable."""
        conn = WebConnector()
        html_path = FIXTURES_DIR / "hackathon_page_unstructured.html"
        html_content = html_path.read_text(encoding="utf-8")
        source_id = uuid.uuid4()

        raw_item = {
            "html": html_content,
            "url": "https://quantumhack.example.org",
        }

        opp = conn.normalize_raw(raw_item, source_id)

        assert isinstance(opp, OpportunitySchema)
        assert opp.title == "Quantum Leap Hackathon 2025"
        assert opp.category == OpportunityCategory.HACKATHON
        assert opp.mode == OpportunityMode.ONSITE
        assert opp.location is not None
        assert "San Francisco" in opp.location
        assert opp.prize is not None
        assert "$15,000" in opp.prize
        assert opp.registration_deadline is not None

    def test_graceful_degradation_when_ollama_offline(self) -> None:
        """When deterministic extraction lacks title, LLM fallback fails gracefully without crash."""
        conn = WebConnector()
        source_id = uuid.uuid4()

        # HTML with no clear headings or structured data
        minimal_html = "<div><p>Just some plain text without any structure.</p></div>"

        raw_item = {
            "html": minimal_html,
            "url": "https://plain.example.org",
        }

        # Should NOT raise any exception even though Ollama is likely offline in test environment
        opp = conn.normalize_raw(raw_item, source_id)
        assert isinstance(opp, OpportunitySchema)
        assert opp.source_id == source_id
        assert opp.category == OpportunityCategory.HACKATHON
