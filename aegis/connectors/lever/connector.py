"""
Aegis — Lever Postings API Connector

Fetches public job postings from the Lever Postings API:
GET https://api.lever.co/v0/postings/{site}
No authentication required for public company sites.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from connectors.base import BaseConnector, ConnectorMetadata, HealthCheckResult, RawFetchResult
from core.schemas.domain import OpportunityCategory, OpportunityMode, OpportunitySchema


class LeverConnector(BaseConnector):
    """Connector for public Lever Postings API."""

    BASE_URL = "https://api.lever.co/v0/postings"

    @property
    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            name="Lever Postings API Connector",
            source_type="api",
            description="Collects structured job and internship opportunities from public Lever postings sites",
            version="1.0.0",
        )

    def _get_site_url(self, config: dict[str, Any]) -> str:
        site = config.get("site") or config.get("company_slug")
        if not site:
            raise ValueError("Lever connector requires 'site' in config")
        mode = config.get("mode", "json")
        return f"{self.BASE_URL}/{site}?mode={mode}"

    async def fetch(self, config: dict[str, Any]) -> RawFetchResult:
        """Fetch postings JSON from Lever API."""
        url = self._get_site_url(config)
        timeout = config.get("timeout_seconds", 20.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            raw_text = resp.text
            data = resp.json()

        postings = data if isinstance(data, list) else []
        return RawFetchResult.from_payload(raw_text, postings)

    def normalize_raw(
        self,
        raw_item: dict[str, Any],
        source_id: uuid.UUID,
    ) -> OpportunitySchema:
        """Transform a raw Lever posting dictionary into an OpportunitySchema."""
        ext_id = str(raw_item.get("id", ""))
        title = raw_item.get("text", "Untitled Position").strip()
        url = raw_item.get("hostedUrl", "") or raw_item.get("applyUrl", "")

        categories = raw_item.get("categories") or {}
        location = categories.get("location") if isinstance(categories, dict) else None
        department = categories.get("department") if isinstance(categories, dict) else None
        team = categories.get("team") if isinstance(categories, dict) else None

        description = raw_item.get("descriptionPlain") or raw_item.get("description", "")

        # Infer category
        title_lower = title.lower()
        if "intern" in title_lower or "co-op" in title_lower or "fellowship" in title_lower:
            category = OpportunityCategory.INTERNSHIP
        else:
            category = OpportunityCategory.JOB

        # Map workplaceType
        workplace_type = (raw_item.get("workplaceType") or "").lower()
        if workplace_type == "remote" or "remote" in (location or "").lower():
            mode = OpportunityMode.REMOTE
        elif workplace_type == "hybrid":
            mode = OpportunityMode.HYBRID
        elif workplace_type in ("on-site", "onsite") or location:
            mode = OpportunityMode.ONSITE
        else:
            mode = None

        # Parse createdAt timestamp (millisecond epoch)
        created_at_ms = raw_item.get("createdAt")
        published_at = None
        if created_at_ms and isinstance(created_at_ms, (int, float)):
            try:
                published_at = datetime.fromtimestamp(created_at_ms / 1000.0, tz=UTC)
            except Exception:
                published_at = None

        skills_themes = [d for d in [department, team] if d]

        # Field evidence
        evidence = {
            "title": f"Title extracted from Lever listing: '{title}'",
            "category": f"Categorized as {category.value} based on title keywords",
        }
        if location:
            evidence["location"] = f"Location declared as: '{location}'"
        if workplace_type:
            evidence["mode"] = f"Workplace type specified as: '{workplace_type}'"

        item_hash = hashlib.sha256(f"{ext_id}:{title}:{location}:{created_at_ms}".encode()).hexdigest()

        now = datetime.now(UTC)
        return OpportunitySchema(
            id=uuid.uuid4(),
            source_id=source_id,
            external_id=ext_id,
            title=title,
            category=category,
            organizer=raw_item.get("company_name"),
            url=url,
            description=description,
            registration_deadline=None,
            start_date=None,
            end_date=None,
            location=location,
            mode=mode,
            eligibility_text=None,
            team_size_min=None,
            team_size_max=None,
            prize=None,
            skills_themes=skills_themes,
            evidence=evidence,
            content_hash=item_hash,
            published_at=published_at,
            collected_at=now,
            created_at=now,
            updated_at=now,
        )

    async def health_check(self, config: dict[str, Any]) -> HealthCheckResult:
        """Verify Lever API responds for the given site slug."""
        start = time.perf_counter()
        try:
            url = self._get_site_url(config)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers={"Accept": "application/json"})
                latency = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    count = len(data) if isinstance(data, list) else 0
                    return HealthCheckResult(
                        healthy=True,
                        status_code=200,
                        latency_ms=latency,
                        message=f"Lever site reachable, {count} active postings found",
                    )
                return HealthCheckResult(
                    healthy=False,
                    status_code=resp.status_code,
                    latency_ms=latency,
                    message=f"Lever returned HTTP {resp.status_code}",
                )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckResult(
                healthy=False,
                status_code=None,
                latency_ms=latency,
                message=f"Connection failed: {exc}",
            )
