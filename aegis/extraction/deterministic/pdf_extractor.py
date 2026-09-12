"""
Aegis — Deterministic PDF Text Extractor

Enforces strict MIME validation, magic-byte checking, file size limits,
and deterministic extraction of plain text from PDF documents prior to any LLM processing.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PyPDF2 import PdfReader

# Hard upload constraints
MAX_RESUME_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
ALLOWED_MIME_TYPES = {"application/pdf"}
PDF_MAGIC_BYTES = b"%PDF-"


class PDFExtractionError(Exception):
    """Base exception for PDF validation and extraction failures."""

    pass


class InvalidFileTypeError(PDFExtractionError):
    """Raised when file does not have valid PDF magic bytes or MIME type."""

    pass


class FileSizeLimitExceededError(PDFExtractionError):
    """Raised when uploaded file exceeds the configured size limit."""

    pass


class MalformedPDFError(PDFExtractionError):
    """Raised when the PDF structure is corrupted or unreadable."""

    pass


@dataclass(frozen=True)
class ExtractedPDFResult:
    """Deterministic extraction outcome."""

    raw_text: str
    page_count: int
    char_count: int
    is_empty: bool


def validate_pdf_bytes(
    file_bytes: bytes,
    content_type: str | None = None,
    max_size_bytes: int = MAX_RESUME_SIZE_BYTES,
) -> None:
    """
    Validate that raw bytes constitute a safe, valid PDF file under the size threshold.
    """
    # 1. Size check
    if len(file_bytes) > max_size_bytes:
        raise FileSizeLimitExceededError(
            f"File size {len(file_bytes)} bytes exceeds maximum allowed limit of {max_size_bytes} bytes."
        )

    if len(file_bytes) == 0:
        raise MalformedPDFError("Uploaded file is empty (0 bytes).")

    # 2. MIME type check if provided
    if content_type and content_type.lower() not in ALLOWED_MIME_TYPES:
        raise InvalidFileTypeError(
            f"Invalid content type '{content_type}'. Only 'application/pdf' is supported."
        )

    # 3. Magic bytes verification (must start with %PDF-)
    if not file_bytes.startswith(PDF_MAGIC_BYTES):
        raise InvalidFileTypeError(
            "File header does not match valid PDF magic bytes ('%PDF-'). File may be corrupted or disguised."
        )


def extract_text_from_pdf_bytes(
    file_bytes: bytes,
    content_type: str | None = None,
    max_size_bytes: int = MAX_RESUME_SIZE_BYTES,
) -> ExtractedPDFResult:
    """
    Deterministically extract all text content from a PDF document.

    Raises:
        FileSizeLimitExceededError if file exceeds size limit.
        InvalidFileTypeError if magic bytes or MIME check fails.
        MalformedPDFError if PDF parser encounters unrecoverable corruption.
    """
    validate_pdf_bytes(file_bytes, content_type=content_type, max_size_bytes=max_size_bytes)

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        raise MalformedPDFError(f"Failed to parse PDF structure: {exc}") from exc

    if reader.is_encrypted:
        try:
            # Attempt blank password decrypt
            decrypt_success = reader.decrypt("")
            if decrypt_success == 0:
                raise MalformedPDFError("Encrypted/password-protected PDFs are not supported.")
        except Exception as exc:
            raise MalformedPDFError("Encrypted/password-protected PDFs are not supported.") from exc

    extracted_pages = []
    try:
        for _page_idx, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    extracted_pages.append(page_text)
            except Exception:
                # Log page skip without crashing entire extraction
                continue
    except Exception as exc:
        raise MalformedPDFError(
            f"Corrupted PDF stream encountered during text extraction: {exc}"
        ) from exc

    full_text = "\n\n".join(extracted_pages).strip()
    return ExtractedPDFResult(
        raw_text=full_text,
        page_count=len(reader.pages),
        char_count=len(full_text),
        is_empty=(len(full_text) == 0),
    )
