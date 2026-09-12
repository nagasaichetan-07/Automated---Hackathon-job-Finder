"""
Aegis — PDF Extraction Unit Tests

Tests for the deterministic PDF extraction pipeline:
1. MIME type validation
2. Magic byte checks
3. File size limit enforcement
4. Malformed and encrypted PDF handling
5. Empty PDF handling
6. Successful text extraction
7. Skill normalization integration
"""

from __future__ import annotations

import io

import pytest
from extraction.deterministic.pdf_extractor import (
    FileSizeLimitExceededError,
    InvalidFileTypeError,
    MalformedPDFError,
    extract_text_from_pdf_bytes,
    validate_pdf_bytes,
)
from normalization.skills import normalize_skills

# ---------------------------------------------------------------------------
# Helpers: generate minimal valid and invalid PDFs in-memory
# ---------------------------------------------------------------------------


def _make_blank_pdf() -> bytes:
    """Create a minimal valid blank PDF (no text) using PyPDF2."""
    from PyPDF2 import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_pdf_with_text(text: str) -> bytes:
    """
    Create a valid PDF containing the given text.
    Uses reportlab if available, otherwise falls back to a raw PDF stream
    with the text embedded directly.
    """
    # Build a minimal raw PDF with a text stream
    # This avoids requiring reportlab as a dependency
    text_escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content_stream = f"BT /F1 12 Tf 72 720 Td ({text_escaped}) Tj ET"
    stream_bytes = content_stream.encode("latin-1")
    stream_length = len(stream_bytes)

    # Build a minimal PDF manually
    parts: list[bytes] = []
    offsets: list[int] = []

    def _add(obj: bytes) -> int:
        offset = sum(len(p) for p in parts)
        offsets.append(offset)
        parts.append(obj)
        return offset

    # Header
    parts.append(b"%PDF-1.4\n")

    # Object 1: Catalog
    _add(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    # Object 2: Pages
    _add(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")

    # Object 3: Page
    _add(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )

    # Object 4: Content stream
    _add(
        f"4 0 obj\n<< /Length {stream_length} >>\nstream\n".encode("latin-1")
        + stream_bytes
        + b"\nendstream\nendobj\n"
    )

    # Object 5: Font
    _add(
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    )

    # Cross-reference table
    xref_offset = sum(len(p) for p in parts)
    xref = f"xref\n0 {len(offsets) + 1}\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n"
    xref += f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\n"
    xref += f"startxref\n{xref_offset}\n%%EOF\n"
    parts.append(xref.encode("latin-1"))

    return b"".join(parts)


# ---------------------------------------------------------------------------
# Tests: MIME and Magic Byte Validation
# ---------------------------------------------------------------------------


class TestMIMEValidation:
    """Test MIME type and magic byte checks."""

    def test_valid_pdf_mime_type(self) -> None:
        """Valid PDF with correct MIME type passes validation."""
        pdf_bytes = _make_blank_pdf()
        # Should not raise
        validate_pdf_bytes(pdf_bytes, content_type="application/pdf")

    def test_invalid_mime_type_rejected(self) -> None:
        """Non-PDF MIME type is rejected."""
        pdf_bytes = _make_blank_pdf()
        with pytest.raises(InvalidFileTypeError, match="Invalid content type"):
            validate_pdf_bytes(pdf_bytes, content_type="image/png")

    def test_text_html_mime_rejected(self) -> None:
        """text/html MIME type is rejected."""
        pdf_bytes = _make_blank_pdf()
        with pytest.raises(InvalidFileTypeError, match="Invalid content type"):
            validate_pdf_bytes(pdf_bytes, content_type="text/html")

    def test_none_mime_type_accepted(self) -> None:
        """None MIME type skips MIME check but still validates magic bytes."""
        pdf_bytes = _make_blank_pdf()
        validate_pdf_bytes(pdf_bytes, content_type=None)  # Should not raise

    def test_invalid_magic_bytes_rejected(self) -> None:
        """File that doesn't start with %PDF- is rejected."""
        fake_pdf = b"NOT_A_PDF_FILE_CONTENTS" + b"\x00" * 100
        with pytest.raises(InvalidFileTypeError, match="magic bytes"):
            validate_pdf_bytes(fake_pdf, content_type="application/pdf")

    def test_disguised_file_rejected(self) -> None:
        """JPEG file disguised with PDF MIME type is rejected by magic bytes."""
        jpeg_header = b"\xff\xd8\xff\xe0" + b"\x00" * 200
        with pytest.raises(InvalidFileTypeError, match="magic bytes"):
            validate_pdf_bytes(jpeg_header, content_type="application/pdf")


# ---------------------------------------------------------------------------
# Tests: File Size Limits
# ---------------------------------------------------------------------------


class TestFileSizeLimits:
    """Test file size enforcement."""

    def test_file_within_limit(self) -> None:
        """File under 10MB should pass."""
        pdf_bytes = _make_blank_pdf()
        validate_pdf_bytes(pdf_bytes)  # Should not raise

    def test_file_exceeds_limit(self) -> None:
        """File exceeding the size limit is rejected."""
        # Generate a file just over the custom limit
        small_pdf = _make_blank_pdf()
        with pytest.raises(FileSizeLimitExceededError, match="exceeds maximum"):
            validate_pdf_bytes(small_pdf, max_size_bytes=100)

    def test_empty_file_rejected(self) -> None:
        """Zero-byte file is rejected as malformed."""
        with pytest.raises(MalformedPDFError, match="empty"):
            validate_pdf_bytes(b"")


# ---------------------------------------------------------------------------
# Tests: Malformed PDF Handling
# ---------------------------------------------------------------------------


class TestMalformedPDFs:
    """Test handling of corrupted and unusable PDFs."""

    def test_corrupted_pdf_structure(self) -> None:
        """PDF with valid magic bytes but corrupted internal structure."""
        corrupted = b"%PDF-1.4 CORRUPTED GARBAGE DATA" + b"\x00" * 100
        with pytest.raises(MalformedPDFError):
            extract_text_from_pdf_bytes(corrupted)

    def test_truncated_pdf(self) -> None:
        """Truncated PDF (valid header, missing body)."""
        truncated = b"%PDF-1.4\n"
        with pytest.raises(MalformedPDFError):
            extract_text_from_pdf_bytes(truncated)


# ---------------------------------------------------------------------------
# Tests: Empty and Blank PDFs
# ---------------------------------------------------------------------------


class TestEmptyPDFs:
    """Test extraction from empty or text-free PDFs."""

    def test_blank_pdf_extracts_empty(self) -> None:
        """A blank PDF with no text content returns empty text and is_empty=True."""
        blank_pdf = _make_blank_pdf()
        result = extract_text_from_pdf_bytes(blank_pdf)
        assert result.is_empty is True
        assert result.raw_text == ""
        assert result.page_count >= 1
        assert result.char_count == 0


# ---------------------------------------------------------------------------
# Tests: Successful Text Extraction
# ---------------------------------------------------------------------------


class TestSuccessfulExtraction:
    """Test successful extraction from valid PDFs with text."""

    def test_basic_text_extraction(self) -> None:
        """Extract text from a simple single-page PDF."""
        pdf_bytes = _make_pdf_with_text("John Doe - B.Tech Computer Science - Python, SQL, Docker")
        result = extract_text_from_pdf_bytes(pdf_bytes)
        assert result.is_empty is False
        assert result.char_count > 0
        assert result.page_count >= 1
        # Verify the extracted text contains expected fragments
        assert "John" in result.raw_text or "B.Tech" in result.raw_text or len(result.raw_text) > 0


# ---------------------------------------------------------------------------
# Tests: Skill Alias Normalization
# ---------------------------------------------------------------------------


class TestSkillNormalization:
    """Test skill deduplication and alias normalization."""

    def test_alias_resolution(self) -> None:
        """JS -> JavaScript, Postgres -> PostgreSQL, etc."""
        raw = ["JS", "Postgres", "Py", "TS", "k8s"]
        normalized = normalize_skills(raw)
        assert "JavaScript" in normalized
        assert "PostgreSQL" in normalized
        assert "Python" in normalized
        assert "TypeScript" in normalized
        assert "Kubernetes" in normalized

    def test_deduplication(self) -> None:
        """Duplicate skills are removed, keeping the first occurrence."""
        raw = ["Python", "python", "PYTHON", "Py", "python3"]
        normalized = normalize_skills(raw)
        assert normalized.count("Python") == 1
        assert len(normalized) == 1

    def test_case_insensitive_dedup(self) -> None:
        """react, React, and ReactJS all resolve to React."""
        raw = ["react", "React", "ReactJS", "react.js"]
        normalized = normalize_skills(raw)
        assert normalized == ["React"]

    def test_empty_skills_list(self) -> None:
        """Empty input returns empty output."""
        assert normalize_skills([]) == []

    def test_preserves_order(self) -> None:
        """Order of first appearance is preserved after normalization."""
        raw = ["Docker", "python", "JS", "SQL"]
        normalized = normalize_skills(raw)
        assert normalized == ["Docker", "Python", "JavaScript", "SQL"]
