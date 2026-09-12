"""
Aegis — HTML Extractor Unit Tests

Tests deterministic multi-strategy extraction from HTML pages:
- JSON-LD Schema.org Event/JobPosting extraction
- Open Graph / meta tag extraction
- CSS selector based extraction
- Heuristic text and heading extraction
- Strategy precedence and evidence preservation
- Malformed and empty input resilience
"""

from __future__ import annotations

from pathlib import Path

from extraction.deterministic.html_extractor import extract_from_html

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class TestHTMLExtractorJSONLD:
    """Tests JSON-LD extraction strategy."""

    def test_extract_jsonld_event(self) -> None:
        """Verifies full schema.org Event extraction from JSON-LD fixture."""
        html_path = FIXTURES_DIR / "hackathon_page_jsonld.html"
        html_content = html_path.read_text(encoding="utf-8")

        result = extract_from_html(
            html_content=html_content,
            page_url="https://hackathons.example.org/ai-hackathon-2025",
        )

        assert result.has_sufficient_data
        assert result.title is not None
        assert result.title.value == "AI Hackathon Global 2025"
        assert result.title.extraction_method == "json_ld"
        assert result.title.confidence >= 0.90

        # Description
        assert result.description is not None
        assert "50,000" in result.description.value

        # Dates
        assert result.start_date is not None
        assert result.start_date.value.year == 2025
        assert result.start_date.value.month == 10
        assert result.start_date.value.day == 15

        assert result.end_date is not None
        assert result.end_date.value.year == 2025
        assert result.end_date.value.month == 10
        assert result.end_date.value.day == 17

        assert result.registration_deadline is not None
        assert result.registration_deadline.value.year == 2025
        assert result.registration_deadline.value.month == 10
        assert result.registration_deadline.value.day == 1

        # Organizer
        assert result.organizer is not None
        assert result.organizer.value == "AI Foundation"

        # Category
        assert result.category is not None
        assert result.category.value == "hackathon"

        # Evidence dictionary
        evidence = result.to_evidence_dict()
        assert "title" in evidence
        assert "startDate" in evidence["start_date"]
        assert "AI Foundation" in evidence["organizer"]

        # Strategy method tracking
        assert "json_ld" in result.extraction_methods_used


class TestHTMLExtractorOpenGraph:
    """Tests Open Graph meta tag extraction strategy."""

    def test_extract_opengraph_metadata(self) -> None:
        """Verifies extraction of og:title, og:description, og:url, og:site_name."""
        html_path = FIXTURES_DIR / "hackathon_page_opengraph.html"
        html_content = html_path.read_text(encoding="utf-8")

        result = extract_from_html(
            html_content=html_content,
            page_url="https://campushack.example.edu/2025",
        )

        assert result.has_sufficient_data
        assert result.title is not None
        assert result.title.value == "Campus Hack 2025"
        assert result.title.extraction_method == "open_graph"

        assert result.description is not None
        assert "10,000" in result.description.value

        assert result.url is not None
        assert result.url.value == "https://campushack.example.edu/2025"

        assert result.organizer is not None
        assert result.organizer.value == "Tech Students Guild"

        # Heuristic fills in deadline and location
        assert result.registration_deadline is not None
        assert result.registration_deadline.value.year == 2025
        assert result.registration_deadline.value.month == 11

        assert "open_graph" in result.extraction_methods_used
        assert "heuristic" in result.extraction_methods_used


class TestHTMLExtractorCSSSelectors:
    """Tests configurable CSS selector extraction strategy."""

    def test_custom_css_selectors_override_heuristic(self) -> None:
        """Verifies custom CSS selectors extract specified fields directly."""
        html_content = """
        <html>
        <body>
            <div class="event-hero">
                <span class="custom-title">Deep Learning Summit 2026</span>
                <span class="custom-date">2026-03-20</span>
                <span class="custom-host">Stanford AI Group</span>
            </div>
        </body>
        </html>
        """
        selectors = {
            "title": ".custom-title",
            "start_date": ".custom-date",
            "organizer": ".custom-host",
        }

        result = extract_from_html(
            html_content=html_content,
            custom_selectors=selectors,
        )

        assert result.title is not None
        assert result.title.value == "Deep Learning Summit 2026"
        assert result.title.extraction_method == "css_selector"

        assert result.start_date is not None
        assert result.start_date.value.year == 2026
        assert result.start_date.value.month == 3
        assert result.start_date.value.day == 20

        assert result.organizer is not None
        assert result.organizer.value == "Stanford AI Group"
        assert "css_selector" in result.extraction_methods_used


class TestHTMLExtractorHeuristic:
    """Tests heuristic text extraction fallback."""

    def test_heuristic_extraction_unstructured_page(self) -> None:
        """Verifies heuristic headings and keyword extraction on unstructured HTML."""
        html_path = FIXTURES_DIR / "hackathon_page_unstructured.html"
        html_content = html_path.read_text(encoding="utf-8")

        result = extract_from_html(
            html_content=html_content,
            page_url="https://quantumhack.example.org",
        )

        assert result.has_sufficient_data
        assert result.title is not None
        assert "Quantum Leap Hackathon 2025" in result.title.value
        assert result.title.extraction_method == "heuristic"

        # Inferred category
        assert result.category is not None
        assert result.category.value == "hackathon"

        # Inferred mode (onsite)
        assert result.mode is not None
        assert result.mode.value == "onsite"

        # Inferred location
        assert result.location is not None
        assert "San Francisco" in result.location.value

        # Eligibility section
        assert result.eligibility_text is not None
        assert "undergraduate" in result.eligibility_text.value.lower()

        # Prize section
        assert result.prize is not None
        assert "$15,000" in result.prize.value

        # Deadline
        assert result.registration_deadline is not None
        assert result.registration_deadline.value.year == 2025
        assert result.registration_deadline.value.month == 12


class TestHTMLExtractorResilience:
    """Tests resilience to edge cases, malformed HTML, and empty inputs."""

    def test_empty_html_string(self) -> None:
        """Empty HTML returns empty result without throwing exceptions."""
        result = extract_from_html(html_content="", page_url="https://example.com")
        assert not result.has_sufficient_data
        assert result.title is None
        assert result.url is not None  # Falls back to page_url config

    def test_malformed_html_tags(self) -> None:
        """Malformed or unclosed HTML tags parse gracefully."""
        malformed = "<html><body><h1>Unclosed heading<div><p>Some text</p></body>"
        result = extract_from_html(html_content=malformed)
        assert result.title is not None
        assert "Unclosed heading" in result.title.value

    def test_html_with_no_opportunity_content(self) -> None:
        """Generic web page with no opportunity markers returns empty fields."""
        generic_html = "<html><body><p>Hello world. Nothing to see here.</p></body></html>"
        result = extract_from_html(html_content=generic_html)
        assert not result.has_sufficient_data
        assert result.category is None
        assert result.start_date is None
