"""
Aegis — Date Normalizer Unit Tests

Tests date parsing and normalization logic for web-extracted date strings.
Verifies timezone-awareness (UTC), multi-format compatibility, and strict None-on-failure.
"""

from __future__ import annotations

from datetime import UTC

from normalization.dates import extract_date_range, parse_date


class TestParseDate:
    """Tests for parse_date function."""

    def test_iso_8601_dates(self) -> None:
        """Verifies standard ISO date strings parse to UTC."""
        dt = parse_date("2025-10-15")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 10
        assert dt.day == 15
        assert dt.tzinfo == UTC

    def test_iso_8601_with_zulu_time(self) -> None:
        """Verifies ISO strings with Z time component parse accurately."""
        dt = parse_date("2025-10-15T09:30:00Z")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 10
        assert dt.day == 15
        assert dt.hour == 9
        assert dt.minute == 30
        assert dt.tzinfo == UTC

    def test_iso_8601_with_offset(self) -> None:
        """Verifies ISO strings with timezone offsets convert to UTC."""
        # UTC+5:30 -> UTC 04:00:00
        dt = parse_date("2025-10-15T09:30:00+05:30")
        assert dt is not None
        assert dt.tzinfo == UTC
        assert dt.hour == 4
        assert dt.minute == 0

    def test_us_date_format(self) -> None:
        """Verifies MM/DD/YYYY format."""
        dt = parse_date("01/15/2025")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 1
        assert dt.day == 15
        assert dt.tzinfo == UTC

    def test_eu_date_format(self) -> None:
        """Verifies DD.MM.YYYY and DD-MM-YYYY format."""
        dt_dot = parse_date("15.01.2025")
        assert dt_dot is not None
        assert dt_dot.year == 2025
        assert dt_dot.month == 1
        assert dt_dot.day == 15
        assert dt_dot.tzinfo == UTC

        dt_dash = parse_date("15-01-2025")
        assert dt_dash is not None
        assert dt_dash.year == 2025
        assert dt_dash.month == 1
        assert dt_dash.day == 15

    def test_natural_language_dates(self) -> None:
        """Verifies natural language date strings with ordinal suffixes."""
        dt1 = parse_date("January 15, 2025")
        assert dt1 is not None
        assert (dt1.year, dt1.month, dt1.day) == (2025, 1, 15)

        dt2 = parse_date("Jan 15th 2025")
        assert dt2 is not None
        assert (dt2.year, dt2.month, dt2.day) == (2025, 1, 15)

        dt3 = parse_date("15th Jan 2025")
        assert dt3 is not None
        assert (dt3.year, dt3.month, dt3.day) == (2025, 1, 15)

        dt4 = parse_date("15 January 2025")
        assert dt4 is not None
        assert (dt4.year, dt4.month, dt4.day) == (2025, 1, 15)

    def test_month_year_format(self) -> None:
        """Verifies month-year defaults to 1st of month."""
        dt = parse_date("Oct 2025")
        assert dt is not None
        assert (dt.year, dt.month, dt.day) == (2025, 10, 1)
        assert dt.tzinfo == UTC

    def test_invalid_and_empty_inputs_return_none(self) -> None:
        """Per §2.4: Never guess dates if input is unparseable or absent."""
        assert parse_date(None) is None
        assert parse_date("") is None
        assert parse_date("   ") is None
        assert parse_date("not-a-date") is None
        assert parse_date("tomorrow morning") is None
        assert parse_date("TBD") is None
        assert parse_date("99/99/9999") is None


class TestExtractDateRange:
    """Tests for extract_date_range function."""

    def test_date_range_with_to(self) -> None:
        """Tests 'date to date' range extraction."""
        start, end = extract_date_range("2025-10-15 to 2025-10-17")
        assert start is not None and end is not None
        assert start.day == 15
        assert end.day == 17

    def test_date_range_with_hyphen(self) -> None:
        """Tests 'date - date' range extraction."""
        start, end = extract_date_range("January 15, 2025 - January 17, 2025")
        assert start is not None and end is not None
        assert start.day == 15
        assert end.day == 17

    def test_single_date_in_range(self) -> None:
        """Tests single date returns (start, None)."""
        start, end = extract_date_range("2025-10-15")
        assert start is not None
        assert end is None

    def test_empty_range_returns_none_tuple(self) -> None:
        """Tests empty or invalid range returns (None, None)."""
        start, end = extract_date_range("")
        assert start is None
        assert end is None
