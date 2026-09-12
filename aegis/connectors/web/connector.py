"""
Aegis — Web Connector

Full BaseConnector implementation for web page sources (hackathons, job pages, etc.).
Uses the two-stage extraction pipeline mandated by ARCHITECTURE.md:
    WEB → Deterministic Extraction → LLM Fallback → Normalization

Features:
- SSRF-hardened HTTP fetching via RestrictedHttpClient
- Configurable CSS selectors per source
- JSON-LD, Open Graph, heuristic, and LLM extraction strategies
- Category, mode, and date normalization into canonical OpportunitySchema
- Evidence tracking for every extracted field (§2.4)
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from connectors.base import (
    BaseConnector,
    ConnectorMetadata,
    HealthCheckResult,
    RawFetchResult,
    TransientConnectorError,
)
from connectors.web.http_connector import RestrictedHttpClient
from core.schemas.domain import OpportunityCategory, OpportunityMode, OpportunitySchema
from extraction.deterministic.html_extractor import (
    DeterministicExtractionResult,
    ExtractionField,
    extract_from_html,
)
from extraction.llm.opportunity_extractor import LLMExtractionResult, extract_with_llm


def _strip_html(html_text: str | None) -> str:
    """Remove HTML tags and collapse whitespace."""
    if not html_text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", html_text)
    return " ".join(clean.split())


def _resolve_category(
    det: DeterministicExtractionResult,
    llm: LLMExtractionResult | None,
) -> OpportunityCategory:
    """Resolve category from extraction results, defaulting to HACKATHON for web sources."""
    # Check deterministic result first
    if det.category and det.category.value:
        cat_str = str(det.category.value).lower()
        if cat_str == "internship":
            return OpportunityCategory.INTERNSHIP
        if cat_str == "job":
            return OpportunityCategory.JOB
        if cat_str == "hackathon":
            return OpportunityCategory.HACKATHON

    # Check LLM result
    if llm and llm.category and llm.category.value:
        cat_str = str(llm.category.value).lower()
        if cat_str == "internship":
            return OpportunityCategory.INTERNSHIP
        if cat_str == "job":
            return OpportunityCategory.JOB
        if cat_str == "hackathon":
            return OpportunityCategory.HACKATHON

    # Default for web sources is hackathon
    return OpportunityCategory.HACKATHON


def _resolve_mode(
    det: DeterministicExtractionResult,
    llm: LLMExtractionResult | None,
) -> OpportunityMode | None:
    """Resolve participation mode from extraction results."""
    for result in [det, llm]:
        if result and hasattr(result, "mode") and result.mode and result.mode.value:
            mode_str = str(result.mode.value).lower()
            if mode_str == "remote":
                return OpportunityMode.REMOTE
            if mode_str == "onsite":
                return OpportunityMode.ONSITE
            if mode_str == "hybrid":
                return OpportunityMode.HYBRID
    return None


def _get_field_value(
    det: DeterministicExtractionResult,
    llm: LLMExtractionResult | None,
    field_name: str,
) -> Any:
    """Get the best value for a field from deterministic then LLM results."""
    det_field = getattr(det, field_name, None)
    if isinstance(det_field, ExtractionField) and det_field.value is not None:
        return det_field.value

    if llm:
        llm_field = getattr(llm, field_name, None)
        if llm_field and hasattr(llm_field, "value") and llm_field.value is not None:
            return llm_field.value

    return None


class WebConnector(BaseConnector):
    """Connector for web page sources (hackathons, job listings, events)."""

    @property
    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            name="Web Page Connector",
            source_type="web",
            description=(
                "Extracts opportunity/hackathon data from web pages using "
                "deterministic HTML parsing (JSON-LD, Open Graph, CSS selectors) "
                "with LLM-assisted fallback"
            ),
            version="1.0.0",
        )

    def _get_http_client(self, config: dict[str, Any]) -> RestrictedHttpClient:
        """Create a domain-restricted HTTP client from source config."""
        url = config.get("url", "")
        domain_allowlist = config.get("domain_allowlist", [])

        # Auto-add the configured URL's domain to the allowlist
        if url:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.hostname:
                domain_allowlist = list(set(domain_allowlist) | {parsed.hostname})

        return RestrictedHttpClient(
            domain_allowlist=domain_allowlist,
            rate_limit_per_sec=config.get("rate_limit_per_sec", 1.0),
            timeout_seconds=config.get("timeout_seconds", 20.0),
        )

    async def fetch(self, config: dict[str, Any]) -> RawFetchResult:
        """
        Fetch HTML content from the configured URL using SSRF-hardened HTTP client.
        Returns a RawFetchResult with the HTML as raw_payload and a single record
        containing the page HTML and metadata.
        """
        url = config.get("url", "")
        if not url:
            raise ValueError("Web connector requires 'url' in config")

        http_client = self._get_http_client(config)

        try:
            response = await http_client.get(
                url,
                headers={
                    "User-Agent": "Aegis/1.0 (Opportunity Intelligence Platform)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            response.raise_for_status()
            html_content = response.text
        except httpx.HTTPStatusError as exc:
            raise TransientConnectorError(
                f"HTTP {exc.response.status_code} fetching {url}"
            ) from exc
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise TransientConnectorError(f"Network error fetching {url}: {exc}") from exc

        # Return as a single "record" representing the page
        records = [{
            "html": html_content,
            "url": url,
            "fetched_at": datetime.now(UTC).isoformat(),
        }]

        return RawFetchResult.from_payload(html_content, records)

    def normalize_raw(
        self,
        raw_item: dict[str, Any],
        source_id: uuid.UUID,
    ) -> OpportunitySchema:
        """
        Transform a raw web page record into an OpportunitySchema.
        Runs the two-stage extraction pipeline:
        1. Deterministic extraction (JSON-LD, Open Graph, CSS, heuristic)
        2. LLM fallback (only if deterministic yields insufficient data)
        """
        html_content = raw_item.get("html", "")
        page_url = raw_item.get("url", "")
        custom_selectors = raw_item.get("selectors")  # Optional per-source selectors

        # Stage 1: Deterministic extraction
        det_result = extract_from_html(
            html_content=html_content,
            page_url=page_url,
            custom_selectors=custom_selectors,
        )

        # Stage 2: LLM fallback (only if deterministic is insufficient)
        llm_result: LLMExtractionResult | None = None
        if not det_result.has_sufficient_data:
            try:
                llm_result = asyncio.run(extract_with_llm(
                    page_text=det_result.raw_text or _strip_html(html_content),
                    page_url=page_url,
                ))
            except Exception:
                # LLM failure is non-fatal — we continue with deterministic results
                llm_result = None

        # Resolve fields from best available source
        title = _get_field_value(det_result, llm_result, "title") or "Untitled Opportunity"
        description = _get_field_value(det_result, llm_result, "description")
        location = _get_field_value(det_result, llm_result, "location")
        organizer = _get_field_value(det_result, llm_result, "organizer")
        eligibility_text = _get_field_value(det_result, llm_result, "eligibility_text")
        prize = _get_field_value(det_result, llm_result, "prize")

        # Dates
        start_date = _get_field_value(det_result, llm_result, "start_date")
        end_date = _get_field_value(det_result, llm_result, "end_date")
        reg_deadline = _get_field_value(det_result, llm_result, "registration_deadline")

        # Category and mode
        category = _resolve_category(det_result, llm_result)
        mode = _resolve_mode(det_result, llm_result)

        # URL from extraction or config
        url = _get_field_value(det_result, llm_result, "url") or page_url

        # Skills/themes
        skills: list[str] = []
        if det_result.skills_themes:
            skills = det_result.skills_themes
        if llm_result and llm_result.skills_themes:
            existing = {s.lower() for s in skills}
            for s in llm_result.skills_themes:
                if s.lower() not in existing:
                    skills.append(s)
                    existing.add(s.lower())

        # Build evidence from both extraction stages
        evidence = det_result.to_evidence_dict()
        if llm_result:
            llm_evidence = llm_result.to_evidence_dict()
            for k, v in llm_evidence.items():
                if k not in evidence:
                    evidence[k] = v

        # Generate external_id from URL hash
        ext_id = hashlib.sha256(page_url.encode("utf-8")).hexdigest()[:16]

        # Content hash for dedup
        content_hash = hashlib.sha256(
            f"{ext_id}:{title}:{description or ''}:{str(start_date)}".encode()
        ).hexdigest()

        now = datetime.now(UTC)
        return OpportunitySchema(
            id=uuid.uuid4(),
            source_id=source_id,
            external_id=ext_id,
            title=str(title),
            category=category,
            organizer=str(organizer) if organizer else None,
            url=str(url),
            description=str(description) if description else None,
            registration_deadline=reg_deadline if isinstance(reg_deadline, datetime) else None,
            start_date=start_date if isinstance(start_date, datetime) else None,
            end_date=end_date if isinstance(end_date, datetime) else None,
            location=str(location) if location else None,
            mode=mode,
            eligibility_text=str(eligibility_text) if eligibility_text else None,
            team_size_min=None,
            team_size_max=None,
            prize=str(prize) if prize else None,
            skills_themes=skills,
            evidence=evidence,
            content_hash=content_hash,
            published_at=None,
            collected_at=now,
            created_at=now,
            updated_at=now,
        )

    async def health_check(self, config: dict[str, Any]) -> HealthCheckResult:
        """Perform a lightweight HTTP check against the configured URL."""
        url = config.get("url", "")
        if not url:
            return HealthCheckResult(
                healthy=False,
                message="No URL configured",
            )

        start = time.perf_counter()
        try:
            http_client = self._get_http_client(config)
            response = await http_client.get(url)
            latency = (time.perf_counter() - start) * 1000

            if response.status_code == 200:
                return HealthCheckResult(
                    healthy=True,
                    status_code=200,
                    latency_ms=latency,
                    message=f"Web page reachable (HTTP 200), {len(response.text)} bytes",
                )
            return HealthCheckResult(
                healthy=False,
                status_code=response.status_code,
                latency_ms=latency,
                message=f"Web page returned HTTP {response.status_code}",
            )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckResult(
                healthy=False,
                status_code=None,
                latency_ms=latency,
                message=f"Connection failed: {exc}",
            )
