"""
Aegis — Greenhouse Job Board Connector

Fetches public job postings from Greenhouse Job Board API:
GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
No authentication required for public boards.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from connectors.base import BaseConnector, ConnectorMetadata, HealthCheckResult, RawFetchResult
from core.schemas.domain import OpportunityCategory, OpportunityMode, OpportunitySchema


def _strip_html(html_text: str | None) -> str:
    """Remove HTML tags and collapse whitespace."""
    if not html_text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", html_text)
    return " ".join(clean.split())


class GreenhouseConnector(BaseConnector):
    """Connector for public Greenhouse Job Boards."""

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    @property
    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            name="Greenhouse Job Board Connector",
            source_type="api",
            description="Collects structured job and internship opportunities from public Greenhouse boards",
            version="1.0.0",
        )

    def _get_board_url(self, config: dict[str, Any]) -> str:
        board_token = config.get("board_token") or config.get("company_token")
        if not board_token:
            raise ValueError("Greenhouse connector requires 'board_token' in config")
        return f"{self.BASE_URL}/{board_token}/jobs?content=true"

    async def fetch(self, config: dict[str, Any]) -> RawFetchResult:
        """Fetch jobs JSON from Greenhouse API."""
        url = self._get_board_url(config)
        timeout = config.get("timeout_seconds", 20.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            raw_text = resp.text
            data = resp.json()

        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        return RawFetchResult.from_payload(raw_text, jobs)

    def normalize_raw(
        self,
        raw_item: dict[str, Any],
        source_id: uuid.UUID,
    ) -> OpportunitySchema:
        """Transform a raw Greenhouse job dictionary into an OpportunitySchema."""
        ext_id = str(raw_item.get("id", ""))
        title = raw_item.get("title", "Untitled Position").strip()
        url = raw_item.get("absolute_url", "")
        location_obj = raw_item.get("location") or {}
        location_name = location_obj.get("name") if isinstance(location_obj, dict) else str(location_obj)

        content_html = raw_item.get("content", "")
        description_clean = _strip_html(content_html)

        # Infer category (job vs internship)
        title_lower = title.lower()
        if "intern" in title_lower or "co-op" in title_lower or "apprentice" in title_lower:
            category = OpportunityCategory.INTERNSHIP
        else:
            category = OpportunityCategory.JOB

        # Infer participation mode
        loc_lower = (location_name or "").lower()
        if "remote" in loc_lower or "remote" in title_lower:
            mode = OpportunityMode.REMOTE
        elif "hybrid" in loc_lower or "hybrid" in title_lower:
            mode = OpportunityMode.HYBRID
        elif location_name:
            mode = OpportunityMode.ONSITE
        else:
            mode = None

        # Extract published / updated timestamp
        updated_at_str = raw_item.get("updated_at")
        published_at = None
        if updated_at_str:
            try:
                published_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            except Exception:
                published_at = None

        # Extract departments
        dept_names = []
        for dept in raw_item.get("departments", []):
            if isinstance(dept, dict) and dept.get("name"):
                dept_names.append(dept["name"])

        # Construct evidence snippets
        evidence = {
            "title": f"Title extracted from job listing: '{title}'",
            "category": f"Categorized as {category.value} based on title keywords",
        }
        if location_name:
            evidence["location"] = f"Location declared as: '{location_name}'"

        # Unique content hash for the opportunity item
        item_hash = hashlib.sha256(f"{ext_id}:{title}:{location_name}:{updated_at_str}".encode()).hexdigest()

        now = datetime.now(UTC)
        return OpportunitySchema(
            id=uuid.uuid4(),
            source_id=source_id,
            external_id=ext_id,
            title=title,
            category=category,
            organizer=raw_item.get("company_name"),
            url=url,
            description=description_clean,
            registration_deadline=None,
            start_date=None,
            end_date=None,
            location=location_name,
            mode=mode,
            eligibility_text=None,
            team_size_min=None,
            team_size_max=None,
            prize=None,
            skills_themes=dept_names,
            evidence=evidence,
            content_hash=item_hash,
            published_at=published_at,
            collected_at=now,
            created_at=now,
            updated_at=now,
        )

    async def health_check(self, config: dict[str, Any]) -> HealthCheckResult:
        """Verify Greenhouse API responds for the given board token."""
        start = time.perf_counter()
        try:
            url = self._get_board_url(config)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers={"Accept": "application/json"})
                latency = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    job_count = len(data.get("jobs", []))
                    return HealthCheckResult(
                        healthy=True,
                        status_code=200,
                        latency_ms=latency,
                        message=f"Greenhouse board reachable, {job_count} active jobs found",
                    )
                return HealthCheckResult(
                    healthy=False,
                    status_code=resp.status_code,
                    latency_ms=latency,
                    message=f"Greenhouse returned HTTP {resp.status_code}",
                )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckResult(
                healthy=False,
                status_code=None,
                latency_ms=latency,
                message=f"Connection failed: {exc}",
            )
