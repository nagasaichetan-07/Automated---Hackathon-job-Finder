"""
Aegis — Failure Classifier

Analyzes source collection runs, errors, and extracted data quality
to classify anomalies into actionable FailureClass types.
"""

from __future__ import annotations

from typing import Any

from core.schemas.domain import FailureClass


class FailureClassifier:
    """Classifies connector anomalies into standardized FailureClass categories."""

    @staticmethod
    def classify_failure(
        error_message: str | None = None,
        record_count: int = 0,
        raw_content: str | None = None,
        extraction_stats: dict[str, Any] | None = None,
    ) -> FailureClass:
        """
        Determine the primary failure classification from run signals.
        """
        err_lower = (error_message or "").lower()

        # 1. Timeout / Rate Limit checks
        if any(kw in err_lower for kw in ["timeout", "timed out", "timedout", "429", "rate limit", "too many requests", "retry-after"]):
            return FailureClass.TIMEOUT_OR_RATE_LIMIT

        # 2. Source Unavailable checks
        if any(kw in err_lower for kw in ["500", "502", "503", "504", "connection refused", "name resolution", "dns", "unreachable", "service unavailable"]):
            return FailureClass.SOURCE_UNAVAILABLE

        # 3. Selector Not Found checks
        if any(kw in err_lower for kw in ["selector", "elementnotfound", "nosuchelement", "xpath", "css", "none-type object has no attribute", "could not find element"]):
            return FailureClass.SELECTOR_NOT_FOUND

        # 4. Schema Drift & Field Quality checks (when extraction stats are present)
        if extraction_stats:
            missing_titles = extraction_stats.get("missing_titles_pct", 0.0)
            missing_urls = extraction_stats.get("missing_urls_pct", 0.0)
            if missing_titles > 0.5 or missing_urls > 0.5:
                return FailureClass.SCHEMA_DRIFT

            low_confidence_pct = extraction_stats.get("low_confidence_pct", 0.0)
            if low_confidence_pct > 0.4:
                return FailureClass.FIELD_QUALITY_DROP

        # 5. Zero Records check
        if record_count == 0 and not error_message:
            return FailureClass.ZERO_RECORDS

        if "schema" in err_lower or "validationerror" in err_lower:
            return FailureClass.SCHEMA_DRIFT

        if "zero records" in err_lower or record_count == 0:
            return FailureClass.ZERO_RECORDS

        # Default fallback for selector/extraction failures
        return FailureClass.SELECTOR_NOT_FOUND
