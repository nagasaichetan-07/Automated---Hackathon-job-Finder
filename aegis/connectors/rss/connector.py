"""
Aegis — Generic RSS & Atom Feed Connector

Parses standard RSS 2.0 and Atom 1.0 feeds for opportunity intelligence.
Implements XML entity defense against XXE and entity expansion attacks.
"""

from __future__ import annotations

import email.utils
import hashlib
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any

import httpx
from connectors.base import BaseConnector, ConnectorMetadata, HealthCheckResult, RawFetchResult
from core.schemas.domain import OpportunityCategory, OpportunityMode, OpportunitySchema


def _safe_parse_xml(xml_text: str) -> ET.Element:
    """
    Parse XML text using standard ElementTree.
    Python's standard xml.etree.ElementTree is not vulnerable to external entity expansion (XXE),
    but we forbid DOCTYPE declarations containing entity definitions as a defense-in-depth measure.
    """
    if "<!ENTITY" in xml_text.upper():
        raise ValueError("Potential XML Entity Expansion attack detected: DOCTYPE ENTITY forbidden")
    return ET.fromstring(xml_text)


def _parse_pubdate(date_str: str | None) -> datetime | None:
    """Parse RFC 822 (RSS) or ISO 8601 (Atom) date strings."""
    if not date_str:
        return None
    date_str = date_str.strip()

    # Try RFC 822 / email format (e.g. 'Wed, 02 Oct 2024 13:00:00 GMT')
    try:
        parsed_tuple = email.utils.parsedate_to_datetime(date_str)
        if parsed_tuple:
            return parsed_tuple.astimezone(UTC)
    except Exception:
        pass

    # Try ISO format
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        pass

    return None


class RSSConnector(BaseConnector):
    """Connector for RSS 2.0 and Atom XML feeds."""

    @property
    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            name="Generic RSS & Atom Connector",
            source_type="rss",
            description="Collects opportunity posts from standard RSS 2.0 and Atom XML feeds",
            version="1.0.0",
        )

    def _extract_items_from_xml(self, root: ET.Element) -> list[dict[str, Any]]:
        """Extract item dictionaries from either RSS channel or Atom feed."""
        tag = root.tag.lower()
        items: list[dict[str, Any]] = []

        # RSS 2.0
        if "rss" in tag or root.find("channel") is not None:
            channel = root.find("channel") or root
            for item in channel.findall("item"):
                title_elem = item.find("title")
                link_elem = item.find("link")
                guid_elem = item.find("guid")
                desc_elem = item.find("description")
                pubdate_elem = item.find("pubDate")
                category_elems = item.findall("category")

                items.append({
                    "title": title_elem.text.strip() if title_elem is not None and title_elem.text else "",
                    "link": link_elem.text.strip() if link_elem is not None and link_elem.text else "",
                    "guid": guid_elem.text.strip() if guid_elem is not None and guid_elem.text else "",
                    "description": desc_elem.text.strip() if desc_elem is not None and desc_elem.text else "",
                    "pubDate": pubdate_elem.text.strip() if pubdate_elem is not None and pubdate_elem.text else "",
                    "categories": [c.text.strip() for c in category_elems if c.text],
                })

        # Atom 1.0 (with or without namespaces)
        elif "feed" in tag:
            # Handle potential XML namespace
            ns = {"atom": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
            prefix = "atom:" if ns else ""

            for entry in root.findall(f"{prefix}entry", ns):
                title_elem = entry.find(f"{prefix}title", ns)
                id_elem = entry.find(f"{prefix}id", ns)
                summary_elem = entry.find(f"{prefix}summary", ns) or entry.find(f"{prefix}content", ns)
                updated_elem = entry.find(f"{prefix}updated", ns) or entry.find(f"{prefix}published", ns)

                # Atom link can be in href attribute or text
                link_elem = entry.find(f"{prefix}link", ns)
                link = ""
                if link_elem is not None:
                    link = link_elem.attrib.get("href", "") or (link_elem.text or "").strip()

                items.append({
                    "title": title_elem.text.strip() if title_elem is not None and title_elem.text else "",
                    "link": link,
                    "guid": id_elem.text.strip() if id_elem is not None and id_elem.text else "",
                    "description": summary_elem.text.strip() if summary_elem is not None and summary_elem.text else "",
                    "pubDate": updated_elem.text.strip() if updated_elem is not None and updated_elem.text else "",
                    "categories": [],
                })

        return items

    async def fetch(self, config: dict[str, Any]) -> RawFetchResult:
        """Fetch feed XML from the configured URL."""
        feed_url = config.get("feed_url") or config.get("url")
        if not feed_url:
            raise ValueError("RSS connector requires 'feed_url' in config")

        timeout = config.get("timeout_seconds", 20.0)
        headers = {"User-Agent": "AegisBot/1.0 (+https://github.com/aegis/bot)"}

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(feed_url, headers=headers)
            resp.raise_for_status()
            raw_text = resp.text

        root = _safe_parse_xml(raw_text)
        items = self._extract_items_from_xml(root)
        return RawFetchResult.from_payload(raw_text, items)

    def normalize_raw(
        self,
        raw_item: dict[str, Any],
        source_id: uuid.UUID,
    ) -> OpportunitySchema:
        """Transform a raw feed item into an OpportunitySchema."""
        title = raw_item.get("title", "Untitled Feed Post").strip()
        link = raw_item.get("link", "").strip()
        guid = raw_item.get("guid", "").strip()
        ext_id = guid or link or hashlib.sha256(f"{title}:{link}".encode()).hexdigest()[:16]

        description = raw_item.get("description", "")
        pub_date = _parse_pubdate(raw_item.get("pubDate"))
        categories = raw_item.get("categories", [])

        # Infer category and mode
        full_text = f"{title} {' '.join(categories)} {description}".lower()
        if "hackathon" in full_text:
            category = OpportunityCategory.HACKATHON
        elif "intern" in full_text or "fellowship" in full_text:
            category = OpportunityCategory.INTERNSHIP
        else:
            category = OpportunityCategory.JOB

        # Mode inference
        mode = None
        if "remote" in full_text:
            mode = OpportunityMode.REMOTE
        elif "hybrid" in full_text:
            mode = OpportunityMode.HYBRID

        evidence = {
            "title": f"Extracted from feed entry: '{title}'",
            "category": f"Categorized as {category.value} from content keywords",
        }

        item_hash = hashlib.sha256(f"{ext_id}:{title}:{link}".encode()).hexdigest()
        now = datetime.now(UTC)

        return OpportunitySchema(
            id=uuid.uuid4(),
            source_id=source_id,
            external_id=ext_id,
            title=title,
            category=category,
            organizer=raw_item.get("author") or raw_item.get("feed_title"),
            url=link,
            description=description,
            registration_deadline=None,
            start_date=None,
            end_date=None,
            location=None,
            mode=mode,
            eligibility_text=None,
            team_size_min=None,
            team_size_max=None,
            prize=None,
            skills_themes=categories,
            evidence=evidence,
            content_hash=item_hash,
            published_at=pub_date,
            collected_at=now,
            created_at=now,
            updated_at=now,
        )

    async def health_check(self, config: dict[str, Any]) -> HealthCheckResult:
        """Verify the RSS feed is reachable and valid XML."""
        start = time.perf_counter()
        try:
            feed_url = config.get("feed_url") or config.get("url")
            if not feed_url:
                return HealthCheckResult(healthy=False, message="Missing 'feed_url' in config")

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(feed_url, headers={"User-Agent": "AegisBot/1.0"})
                latency = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    root = _safe_parse_xml(resp.text)
                    items = self._extract_items_from_xml(root)
                    return HealthCheckResult(
                        healthy=True,
                        status_code=200,
                        latency_ms=latency,
                        message=f"RSS feed parsed successfully, {len(items)} items found",
                    )
                return HealthCheckResult(
                    healthy=False,
                    status_code=resp.status_code,
                    latency_ms=latency,
                    message=f"Feed returned HTTP {resp.status_code}",
                )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckResult(
                healthy=False,
                status_code=None,
                latency_ms=latency,
                message=f"Feed validation failed: {exc}",
            )
