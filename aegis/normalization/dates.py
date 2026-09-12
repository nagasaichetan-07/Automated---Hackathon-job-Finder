"""
Aegis — Date Normalization Utility

Robust date parsing for web-extracted date strings.
Handles common formats: ISO 8601, US/EU date conventions, natural language months,
ordinal suffixes, and time ranges. All outputs are timezone-aware UTC datetimes.
Returns None for unparseable strings (never guesses — §2.4).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timezone
from typing import Final

# ---------------------------------------------------------------------------
# Month name lookup tables
# ---------------------------------------------------------------------------

_MONTH_NAMES: Final[dict[str, int]] = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# ---------------------------------------------------------------------------
# Regex patterns for common date formats
# ---------------------------------------------------------------------------

# ISO 8601: "2025-01-15", "2025-01-15T10:30:00Z", "2025-01-15T10:30:00+05:30"
_ISO_PATTERN = re.compile(
    r"(\d{4})-(\d{1,2})-(\d{1,2})"
    r"(?:[T ](\d{1,2}):(\d{2})(?::(\d{2}))?"
    r"(?:Z|([+-]\d{2}:\d{2}))?)?"
)

# US format: "01/15/2025", "1/15/2025"
_US_DATE_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

# EU format: "15.01.2025", "15-01-2025"
_EU_DATE_PATTERN = re.compile(r"(\d{1,2})[.\-](\d{1,2})[.\-](\d{4})")

# Natural language: "January 15, 2025", "Jan 15th 2025", "15 January 2025"
_NATURAL_MDY_PATTERN = re.compile(
    r"(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})",
    re.IGNORECASE,
)
_NATURAL_DMY_PATTERN = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+(\w+),?\s*(\d{4})",
    re.IGNORECASE,
)

# Short month-year: "Jan 2025" (defaults to 1st of month)
_MONTH_YEAR_PATTERN = re.compile(
    r"(\w+)\s+(\d{4})",
    re.IGNORECASE,
)


def _clean_date_string(raw: str) -> str:
    """Strip leading/trailing whitespace, collapse internal whitespace, remove surrounding punctuation."""
    cleaned = raw.strip().strip(".,;:!?")
    cleaned = " ".join(cleaned.split())
    return cleaned


def _make_utc(year: int, month: int, day: int,
              hour: int = 0, minute: int = 0, second: int = 0) -> datetime | None:
    """Safely construct a UTC datetime, returning None for invalid dates."""
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except (ValueError, OverflowError):
        return None


def parse_date(raw: str | None) -> datetime | None:
    """
    Parse a date string into a timezone-aware UTC datetime.

    Supports:
    - ISO 8601: "2025-01-15", "2025-01-15T10:30:00Z"
    - US format: "01/15/2025", "1/15/2025"
    - EU format: "15.01.2025"
    - Natural language: "January 15, 2025", "15th Jan 2025"
    - Month-year: "Jan 2025" (defaults to 1st)

    Returns None for unparseable strings (per §2.4 — never guesses).
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = _clean_date_string(raw)
    if not cleaned:
        return None

    # 1. Try ISO 8601
    m = _ISO_PATTERN.fullmatch(cleaned)
    if not m:
        # Also try as a prefix match for ISO dates embedded in longer strings
        m = _ISO_PATTERN.match(cleaned)

    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hour = int(m.group(4)) if m.group(4) else 0
        minute = int(m.group(5)) if m.group(5) else 0
        second = int(m.group(6)) if m.group(6) else 0

        if m.group(7):
            # Parse timezone offset
            tz_str = m.group(7)
            tz_sign = 1 if tz_str[0] == "+" else -1
            tz_parts = tz_str[1:].split(":")
            tz_hours = int(tz_parts[0])
            tz_minutes = int(tz_parts[1]) if len(tz_parts) > 1 else 0
            offset_seconds = tz_sign * (tz_hours * 3600 + tz_minutes * 60)
            tz = timezone(offset=__import__("datetime").timedelta(seconds=offset_seconds))
            try:
                dt = datetime(year, month, day, hour, minute, second, tzinfo=tz)
                return dt.astimezone(UTC)
            except (ValueError, OverflowError):
                return None

        return _make_utc(year, month, day, hour, minute, second)

    # 2. Try natural language: "January 15, 2025" or "Jan 15th 2025"
    m = _NATURAL_MDY_PATTERN.search(cleaned)
    if m:
        month_str = m.group(1).lower()
        month_num = _MONTH_NAMES.get(month_str)
        if month_num:
            day = int(m.group(2))
            year = int(m.group(3))
            return _make_utc(year, month_num, day)

    # 3. Try natural language: "15 January 2025" or "15th Jan 2025"
    m = _NATURAL_DMY_PATTERN.search(cleaned)
    if m:
        day = int(m.group(1))
        month_str = m.group(2).lower()
        month_num = _MONTH_NAMES.get(month_str)
        if month_num:
            year = int(m.group(3))
            return _make_utc(year, month_num, day)

    # 4. Try US format: "01/15/2025"
    m = _US_DATE_PATTERN.fullmatch(cleaned)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _make_utc(year, month, day)

    # 5. Try EU format: "15.01.2025" or "15-01-2025"
    m = _EU_DATE_PATTERN.fullmatch(cleaned)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _make_utc(year, month, day)

    # 6. Try month-year: "Jan 2025" (defaults to 1st)
    m = _MONTH_YEAR_PATTERN.fullmatch(cleaned)
    if m:
        month_str = m.group(1).lower()
        month_num = _MONTH_NAMES.get(month_str)
        if month_num:
            year = int(m.group(2))
            return _make_utc(year, month_num, 1)

    # 7. Try Python's built-in ISO parsing as last resort
    try:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (ValueError, OverflowError):
        pass

    return None


def extract_date_range(text: str) -> tuple[datetime | None, datetime | None]:
    """
    Extract start and end dates from a date range string.
    Handles formats like: "Jan 15 - Jan 17, 2025", "2025-01-15 to 2025-01-17".

    Returns (start_date, end_date).
    """
    if not text:
        return None, None

    # Split on common range separators (require whitespace around hyphen to avoid splitting inside ISO dates)
    parts = re.split(
        r"(?:\s+(?:to|through|until|–|—|-|→)\s+|\s*[–—→]\s*)",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )

    if len(parts) == 2:
        start = parse_date(parts[0].strip())
        end = parse_date(parts[1].strip())
        return start, end

    # Single date — return as start, no end
    single = parse_date(text)
    return single, None
