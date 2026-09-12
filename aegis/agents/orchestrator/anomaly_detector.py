"""
Aegis — Anomaly Detector

Monitors source health transitions and collection runs to detect actionable anomalies
and trigger the self-healing pipeline.
"""

from __future__ import annotations

from typing import Any

from agents.orchestrator.failure_classifier import FailureClassifier
from core.schemas.domain import FailureClass, SourceHealth


class AnomalyDetector:
    """Detects operational anomalies in connectors and determines repair eligibility."""

    # Failures that can be remediated via connector code repair
    ACTIONABLE_REPAIR_CLASSES: set[FailureClass] = {
        FailureClass.SELECTOR_NOT_FOUND,
        FailureClass.SCHEMA_DRIFT,
        FailureClass.ZERO_RECORDS,
        FailureClass.FIELD_QUALITY_DROP,
    }

    def __init__(self, failure_classifier: FailureClassifier | None = None) -> None:
        self.classifier = failure_classifier or FailureClassifier()

    def evaluate_run_anomaly(
        self,
        health_state: SourceHealth | str,
        consecutive_failures: int,
        error_message: str | None = None,
        record_count: int = 0,
        extraction_stats: dict[str, Any] | None = None,
    ) -> tuple[bool, FailureClass, str]:
        """
        Evaluate whether a source run represents an actionable anomaly requiring self-repair.

        Returns:
            (is_actionable, failure_class, summary_reason)
        """
        health_val = health_state.value if isinstance(health_state, SourceHealth) else health_state

        failure_class = self.classifier.classify_failure(
            error_message=error_message,
            record_count=record_count,
            extraction_stats=extraction_stats,
        )

        is_broken_or_degraded = health_val in [SourceHealth.DEGRADED.value, SourceHealth.BROKEN.value]
        is_actionable = is_broken_or_degraded and (failure_class in self.ACTIONABLE_REPAIR_CLASSES)

        reason = (
            f"Source in {health_val} state ({consecutive_failures} failures). "
            f"Classified failure: {failure_class.value}. "
            f"Actionable for repair: {is_actionable}."
        )

        return is_actionable, failure_class, reason
