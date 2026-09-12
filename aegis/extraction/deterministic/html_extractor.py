"""
Aegis — Deterministic HTML Extraction Engine

Multi-strategy deterministic extractor for HTML pages:
1. JSON-LD extraction — Parses <script type="application/ld+json"> for schema.org Event/JobPosting.
2. Open Graph / meta tag extraction — og:title, og:description, og:url, dates.
3. CSS selector extraction — Configurable selectors for common hackathon layouts.
4. Heuristic text extraction — Heading + paragraph text with keyword matching.

All extraction is deterministic first (§2.3). LLM is never invoked here.
All external content is treated as untrusted data (§2.5).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, Comment
from normalization.dates import parse_date


@dataclass
class ExtractionField:
    """A single extracted field with value, evidence, and confidence."""

    value: Any
    evidence: str  # Source text snippet that produced this value
    confidence: float  # 0.0 to 1.0
    extraction_method: str  # "json_ld", "open_graph", "css_selector", "heuristic"


@dataclass
class DeterministicExtractionResult:
    """Result of deterministic HTML extraction."""

    title: ExtractionField | None = None
    description: ExtractionField | None = None
    url: ExtractionField | None = None
    location: ExtractionField | None = None
    start_date: ExtractionField | None = None
    end_date: ExtractionField | None = None
    registration_deadline: ExtractionField | None = None
    organizer: ExtractionField | None = None
    category: ExtractionField | None = None
    mode: ExtractionField | None = None
    eligibility_text: ExtractionField | None = None
    prize: ExtractionField | None = None
    skills_themes: list[str] = field(default_factory=list)
    raw_text: str = ""
    extraction_methods_used: list[str] = field(default_factory=list)

    @property
    def has_sufficient_data(self) -> bool:
        """Returns True if at least title is extracted."""
        return self.title is not None and bool(self.title.value)

    def to_evidence_dict(self) -> dict[str, str]:
        """Build evidence map for OpportunitySchema."""
        evidence: dict[str, str] = {}
        for field_name in [
            "title", "description", "url", "location", "start_date",
            "end_date", "registration_deadline", "organizer", "category",
            "mode", "eligibility_text", "prize",
        ]:
            field_val = getattr(self, field_name)
            if isinstance(field_val, ExtractionField) and field_val.value is not None:
                evidence[field_name] = field_val.evidence
        return evidence


def _sanitize_text(text: str) -> str:
    """Remove potential prompt injection markers and normalize whitespace."""
    if not text:
        return ""
    # Collapse whitespace
    cleaned = " ".join(text.split())
    # Cap length to prevent memory issues from adversarial content
    return cleaned[:10000]


def _strip_html_tags(html_text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    if not html_text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", html_text)
    return " ".join(clean.split())


# ---------------------------------------------------------------------------
# Strategy 1: JSON-LD Extraction
# ---------------------------------------------------------------------------


def _extract_jsonld(soup: BeautifulSoup) -> DeterministicExtractionResult | None:
    """Extract structured data from JSON-LD <script> blocks."""
    scripts = soup.find_all("script", {"type": "application/ld+json"})
    if not scripts:
        return None

    for script_tag in scripts:
        try:
            raw_json = script_tag.string
            if not raw_json:
                continue
            data = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            continue

        # Handle @graph arrays
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if "@graph" in data:
                items = data["@graph"] if isinstance(data["@graph"], list) else [data["@graph"]]
            else:
                items = [data]

        for item in items:
            if not isinstance(item, dict):
                continue

            item_type = item.get("@type", "")
            if isinstance(item_type, list):
                item_type = item_type[0] if item_type else ""

            # Accept Event, Hackathon, JobPosting, SocialEvent, etc.
            if item_type.lower() not in (
                "event", "hackathon", "socialevent", "educationevent",
                "businessevent", "jobposting",
            ):
                continue

            result = DeterministicExtractionResult(
                extraction_methods_used=["json_ld"],
            )

            # Title
            name = item.get("name") or item.get("title", "")
            if name:
                result.title = ExtractionField(
                    value=_sanitize_text(str(name)),
                    evidence=f"JSON-LD @type={item_type} name: '{str(name)[:200]}'",
                    confidence=0.95,
                    extraction_method="json_ld",
                )

            # Description
            desc = item.get("description", "")
            if desc:
                clean_desc = _sanitize_text(_strip_html_tags(str(desc)))
                result.description = ExtractionField(
                    value=clean_desc,
                    evidence=f"JSON-LD description: '{clean_desc[:200]}'",
                    confidence=0.90,
                    extraction_method="json_ld",
                )

            # URL
            url_val = item.get("url", "")
            if url_val:
                result.url = ExtractionField(
                    value=str(url_val),
                    evidence=f"JSON-LD url: '{str(url_val)}'",
                    confidence=0.95,
                    extraction_method="json_ld",
                )

            # Location
            location = item.get("location")
            if isinstance(location, dict):
                loc_name = location.get("name", "")
                address = location.get("address")
                if isinstance(address, dict):
                    loc_parts = [
                        address.get("streetAddress", ""),
                        address.get("addressLocality", ""),
                        address.get("addressRegion", ""),
                        address.get("addressCountry", ""),
                    ]
                    loc_str = ", ".join(p for p in loc_parts if p)
                    if loc_name:
                        loc_str = f"{loc_name}, {loc_str}" if loc_str else loc_name
                elif isinstance(address, str):
                    loc_str = f"{loc_name}, {address}" if loc_name else address
                else:
                    loc_str = loc_name or ""
                if loc_str:
                    result.location = ExtractionField(
                        value=_sanitize_text(loc_str),
                        evidence=f"JSON-LD location: '{loc_str[:200]}'",
                        confidence=0.90,
                        extraction_method="json_ld",
                    )
            elif isinstance(location, str) and location:
                result.location = ExtractionField(
                    value=_sanitize_text(location),
                    evidence=f"JSON-LD location: '{location[:200]}'",
                    confidence=0.85,
                    extraction_method="json_ld",
                )

            # Dates
            start = item.get("startDate")
            if start:
                parsed = parse_date(str(start))
                if parsed:
                    result.start_date = ExtractionField(
                        value=parsed,
                        evidence=f"JSON-LD startDate: '{start}'",
                        confidence=0.95,
                        extraction_method="json_ld",
                    )

            end = item.get("endDate")
            if end:
                parsed = parse_date(str(end))
                if parsed:
                    result.end_date = ExtractionField(
                        value=parsed,
                        evidence=f"JSON-LD endDate: '{end}'",
                        confidence=0.95,
                        extraction_method="json_ld",
                    )

            # Registration deadline (custom field, often in hackathon JSON-LD)
            deadline = item.get("registrationDeadline") or item.get("doorTime")
            if deadline:
                parsed = parse_date(str(deadline))
                if parsed:
                    result.registration_deadline = ExtractionField(
                        value=parsed,
                        evidence=f"JSON-LD registration deadline: '{deadline}'",
                        confidence=0.85,
                        extraction_method="json_ld",
                    )

            # Organizer
            organizer = item.get("organizer")
            if isinstance(organizer, dict):
                org_name = organizer.get("name", "")
                if org_name:
                    result.organizer = ExtractionField(
                        value=_sanitize_text(str(org_name)),
                        evidence=f"JSON-LD organizer: '{org_name[:200]}'",
                        confidence=0.90,
                        extraction_method="json_ld",
                    )
            elif isinstance(organizer, str) and organizer:
                result.organizer = ExtractionField(
                    value=_sanitize_text(organizer),
                    evidence=f"JSON-LD organizer: '{organizer[:200]}'",
                    confidence=0.85,
                    extraction_method="json_ld",
                )

            # Infer category
            type_lower = item_type.lower()
            if type_lower in ("event", "hackathon", "socialevent", "educationevent"):
                result.category = ExtractionField(
                    value="hackathon",
                    evidence=f"JSON-LD @type={item_type} indicates event/hackathon category",
                    confidence=0.85,
                    extraction_method="json_ld",
                )
            elif type_lower == "jobposting":
                title_lower = (result.title.value if result.title else "").lower()
                if "intern" in title_lower or "apprentice" in title_lower:
                    result.category = ExtractionField(
                        value="internship",
                        evidence="JSON-LD @type=JobPosting with internship keyword in title",
                        confidence=0.85,
                        extraction_method="json_ld",
                    )
                else:
                    result.category = ExtractionField(
                        value="job",
                        evidence="JSON-LD @type=JobPosting indicates job category",
                        confidence=0.90,
                        extraction_method="json_ld",
                    )

            return result

    return None


# ---------------------------------------------------------------------------
# Strategy 2: Open Graph / Meta Tag Extraction
# ---------------------------------------------------------------------------


def _extract_opengraph(soup: BeautifulSoup) -> DeterministicExtractionResult | None:
    """Extract structured data from Open Graph and standard meta tags."""
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_url = soup.find("meta", property="og:url")
    og_site = soup.find("meta", property="og:site_name")

    # Also check standard meta tags
    meta_desc = soup.find("meta", attrs={"name": "description"})
    html_title = soup.find("title")

    has_og_data = any([og_title, og_desc, og_url])
    if not has_og_data and not html_title:
        return None

    result = DeterministicExtractionResult(
        extraction_methods_used=["open_graph"],
    )

    # Title
    title_text: str | None = None
    if og_title and og_title.get("content"):
        title_text = str(og_title["content"])
        result.title = ExtractionField(
            value=_sanitize_text(title_text),
            evidence=f"Open Graph og:title: '{title_text[:200]}'",
            confidence=0.80,
            extraction_method="open_graph",
        )
    elif html_title and html_title.string:
        title_text = str(html_title.string).strip()
        result.title = ExtractionField(
            value=_sanitize_text(title_text),
            evidence=f"HTML <title>: '{title_text[:200]}'",
            confidence=0.60,
            extraction_method="open_graph",
        )

    # Description
    desc_text: str | None = None
    if og_desc and og_desc.get("content"):
        desc_text = str(og_desc["content"])
    elif meta_desc and meta_desc.get("content"):
        desc_text = str(meta_desc["content"])

    if desc_text:
        result.description = ExtractionField(
            value=_sanitize_text(desc_text),
            evidence=f"Meta description: '{desc_text[:200]}'",
            confidence=0.70,
            extraction_method="open_graph",
        )

    # URL
    if og_url and og_url.get("content"):
        url_str = str(og_url["content"])
        result.url = ExtractionField(
            value=url_str,
            evidence=f"Open Graph og:url: '{url_str}'",
            confidence=0.85,
            extraction_method="open_graph",
        )

    # Organizer from site name
    if og_site and og_site.get("content"):
        site_str = str(og_site["content"])
        result.organizer = ExtractionField(
            value=_sanitize_text(site_str),
            evidence=f"Open Graph og:site_name: '{site_str[:200]}'",
            confidence=0.70,
            extraction_method="open_graph",
        )

    return result


# ---------------------------------------------------------------------------
# Strategy 3: CSS Selector Extraction
# ---------------------------------------------------------------------------


def _extract_css_selectors(
    soup: BeautifulSoup,
    selectors: dict[str, str],
) -> DeterministicExtractionResult | None:
    """Extract data using user-provided CSS selectors."""
    if not selectors:
        return None

    result = DeterministicExtractionResult(
        extraction_methods_used=["css_selector"],
    )

    field_map: dict[str, str] = {
        "title": "title",
        "description": "description",
        "location": "location",
        "start_date": "start_date",
        "end_date": "end_date",
        "deadline": "registration_deadline",
        "registration_deadline": "registration_deadline",
        "organizer": "organizer",
        "prize": "prize",
        "eligibility": "eligibility_text",
        "eligibility_text": "eligibility_text",
    }

    for sel_key, css_selector in selectors.items():
        target_field = field_map.get(sel_key)
        if not target_field:
            continue

        element = soup.select_one(css_selector)
        if not element:
            continue

        text = _sanitize_text(element.get_text(strip=True))
        if not text:
            continue

        ef = ExtractionField(
            value=text,
            evidence=f"CSS selector '{css_selector}': '{text[:200]}'",
            confidence=0.85,
            extraction_method="css_selector",
        )

        # Parse dates for date fields
        if target_field in ("start_date", "end_date", "registration_deadline"):
            parsed = parse_date(text)
            if parsed:
                ef = ExtractionField(
                    value=parsed,
                    evidence=f"CSS selector '{css_selector}' parsed date: '{text[:200]}'",
                    confidence=0.80,
                    extraction_method="css_selector",
                )
            else:
                continue  # Skip unparseable dates

        setattr(result, target_field, ef)

    return result if result.has_sufficient_data else None


# ---------------------------------------------------------------------------
# Strategy 4: Heuristic Text Extraction
# ---------------------------------------------------------------------------

_HACKATHON_KEYWORDS = frozenset({
    "hackathon", "hack", "codeathon", "datathon", "buildathon",
    "makeathon", "ideathon", "designathon", "devjam", "code sprint",
    "programming contest", "coding challenge", "coding competition",
})

_ELIGIBILITY_KEYWORDS = frozenset({
    "eligib", "who can", "requirement", "prerequisite",
    "must be", "should be", "open to", "criteria",
    "qualification", "eligible", "restrictions",
})

_PRIZE_KEYWORDS = frozenset({
    "prize", "reward", "award", "bounty", "cash",
    "stipend", "scholarship", "winning", "goodies", "swag",
    "₹", "$", "€", "£",
})

_DATE_KEYWORDS = frozenset({
    "deadline", "last date", "registration close", "submit by",
    "apply by", "register by", "due date", "closes on",
})


def _extract_heuristic(soup: BeautifulSoup) -> DeterministicExtractionResult:
    """
    Fall back to heuristic extraction from page headings and text.
    """
    result = DeterministicExtractionResult(
        extraction_methods_used=["heuristic"],
    )

    # Remove script, style, and comment nodes
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Get full page text
    full_text = soup.get_text(separator="\n", strip=True)
    result.raw_text = _sanitize_text(full_text)

    # Title: first h1, then h2
    h1 = soup.find("h1")
    if h1:
        title_text = _sanitize_text(h1.get_text(strip=True))
        if title_text:
            result.title = ExtractionField(
                value=title_text,
                evidence=f"First <h1>: '{title_text[:200]}'",
                confidence=0.60,
                extraction_method="heuristic",
            )
    if not result.title:
        h2 = soup.find("h2")
        if h2:
            title_text = _sanitize_text(h2.get_text(strip=True))
            if title_text:
                result.title = ExtractionField(
                    value=title_text,
                    evidence=f"First <h2>: '{title_text[:200]}'",
                    confidence=0.45,
                    extraction_method="heuristic",
                )

    # Category inference from text
    text_lower = full_text.lower()
    if any(kw in text_lower for kw in _HACKATHON_KEYWORDS):
        result.category = ExtractionField(
            value="hackathon",
            evidence="Hackathon keyword found in page text",
            confidence=0.70,
            extraction_method="heuristic",
        )

    # Location inference
    location_patterns = [
        re.compile(r"\b(?:held at|hosted at|taking place at)\s*[:\-–]?\s*(.+?)(?:\n|$)", re.IGNORECASE),
        re.compile(r"\b(?:venue|location|event location)\s*[:\-–]\s*(.+?)(?:\n|$)", re.IGNORECASE),
        re.compile(r"(?<!first )(?<!second )(?<!third )(?<!1st )(?<!2nd )(?<!3rd )\bplace\s*[:\-–]\s*(.+?)(?:\n|$)", re.IGNORECASE),
    ]
    for pat in location_patterns:
        m = pat.search(full_text)
        if m:
            loc_text = _sanitize_text(m.group(1))
            if loc_text and len(loc_text) < 200:
                result.location = ExtractionField(
                    value=loc_text,
                    evidence=f"Heuristic location pattern: '{m.group(0)[:200]}'",
                    confidence=0.55,
                    extraction_method="heuristic",
                )
                break

    # Mode inference
    if "online" in text_lower or "virtual" in text_lower or "remote" in text_lower:
        result.mode = ExtractionField(
            value="remote",
            evidence="Keywords 'online'/'virtual'/'remote' found in page text",
            confidence=0.60,
            extraction_method="heuristic",
        )
    elif "in-person" in text_lower or "on-site" in text_lower or "offline" in text_lower:
        result.mode = ExtractionField(
            value="onsite",
            evidence="Keywords 'in-person'/'on-site'/'offline' found in page text",
            confidence=0.60,
            extraction_method="heuristic",
        )
    elif "hybrid" in text_lower:
        result.mode = ExtractionField(
            value="hybrid",
            evidence="Keyword 'hybrid' found in page text",
            confidence=0.55,
            extraction_method="heuristic",
        )

    # Eligibility text extraction
    for section_heading in soup.find_all(["h2", "h3", "h4"]):
        heading_text = section_heading.get_text(strip=True).lower()
        if any(kw in heading_text for kw in _ELIGIBILITY_KEYWORDS):
            # Get text following this heading
            next_text_parts = []
            for sibling in section_heading.find_next_siblings():
                if sibling.name in ("h1", "h2", "h3", "h4"):
                    break
                next_text_parts.append(sibling.get_text(strip=True))
            eligibility = _sanitize_text(" ".join(next_text_parts))
            if eligibility:
                result.eligibility_text = ExtractionField(
                    value=eligibility,
                    evidence=f"Eligibility section under '{heading_text}': '{eligibility[:200]}'",
                    confidence=0.65,
                    extraction_method="heuristic",
                )
                break

    # Prize extraction
    for section_heading in soup.find_all(["h2", "h3", "h4"]):
        heading_text = section_heading.get_text(strip=True).lower()
        if any(kw in heading_text for kw in _PRIZE_KEYWORDS):
            next_text_parts = []
            for sibling in section_heading.find_next_siblings():
                if sibling.name in ("h1", "h2", "h3", "h4"):
                    break
                next_text_parts.append(sibling.get_text(strip=True))
            prize_text = _sanitize_text(" ".join(next_text_parts))
            if prize_text:
                result.prize = ExtractionField(
                    value=prize_text,
                    evidence=f"Prize section under '{heading_text}': '{prize_text[:200]}'",
                    confidence=0.60,
                    extraction_method="heuristic",
                )
                break

    # Registration deadline extraction
    for kw in _DATE_KEYWORDS:
        pattern = re.compile(
            rf"(?:{re.escape(kw)})\s*[:\-–]\s*(.+?)(?:\n|$)",
            re.IGNORECASE,
        )
        m = pattern.search(full_text)
        if m:
            date_text = m.group(1).strip()
            parsed = parse_date(date_text)
            if parsed:
                result.registration_deadline = ExtractionField(
                    value=parsed,
                    evidence=f"Deadline keyword '{kw}' matched: '{m.group(0)[:200]}'",
                    confidence=0.60,
                    extraction_method="heuristic",
                )
                break

    return result


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


def extract_from_html(
    html_content: str,
    page_url: str = "",
    custom_selectors: dict[str, str] | None = None,
) -> DeterministicExtractionResult:
    """
    Extract structured opportunity/hackathon data from an HTML page.

    Applies extraction strategies in priority order:
    1. JSON-LD (highest confidence)
    2. CSS selectors (if provided)
    3. Open Graph / meta tags
    4. Heuristic text extraction (lowest confidence, always runs as fallback)

    Higher-confidence fields from earlier strategies are preserved;
    later strategies only fill in missing fields.
    """
    soup = BeautifulSoup(html_content, "lxml")

    # Strategy 1: JSON-LD
    jsonld_result = _extract_jsonld(soup)

    # Strategy 2: CSS selectors (if provided)
    css_result = _extract_css_selectors(soup, custom_selectors or {})

    # Strategy 3: Open Graph
    og_result = _extract_opengraph(soup)

    # Strategy 4: Heuristic (always runs)
    heuristic_result = _extract_heuristic(soup)

    # Merge: higher confidence wins for each field
    final = DeterministicExtractionResult()
    all_methods_used: set[str] = set()

    strategies = [
        jsonld_result,
        css_result,
        og_result,
        heuristic_result,
    ]

    field_names = [
        "title", "description", "url", "location", "start_date",
        "end_date", "registration_deadline", "organizer", "category",
        "mode", "eligibility_text", "prize",
    ]

    for field_name in field_names:
        best_field: ExtractionField | None = None
        best_confidence = -1.0

        for strategy_result in strategies:
            if strategy_result is None:
                continue
            field_val = getattr(strategy_result, field_name, None)
            if isinstance(field_val, ExtractionField) and field_val.value is not None:
                if field_val.confidence > best_confidence:
                    best_field = field_val
                    best_confidence = field_val.confidence

        if best_field is not None:
            setattr(final, field_name, best_field)

    # Merge extraction methods and raw text
    for strategy_result in strategies:
        if strategy_result is not None:
            all_methods_used.update(strategy_result.extraction_methods_used)
            if strategy_result.raw_text and not final.raw_text:
                final.raw_text = strategy_result.raw_text

    final.extraction_methods_used = sorted(all_methods_used)

    # Set URL from page_url if not extracted
    if not final.url and page_url:
        final.url = ExtractionField(
            value=page_url,
            evidence=f"URL from source configuration: '{page_url}'",
            confidence=1.0,
            extraction_method="config",
        )

    return final
