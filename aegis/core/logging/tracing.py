"""
Aegis — Structured Tracing & Telemetry

Provides OpenTelemetry-compatible tracing spans, correlation ID propagation,
step duration tracking, and model/configuration tagging across collection,
extraction, matching, and self-healing.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Generator

logger = logging.getLogger("aegis.telemetry")


@dataclass
class TraceSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start_time: float
    end_time: float | None = None
    duration_ms: float | None = None
    status: str = "IN_PROGRESS"
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


class TelemetryStore:
    """In-memory telemetry store for recording active spans and performance metrics."""

    _spans: list[TraceSpan] = []

    @classmethod
    def record_span(cls, span: TraceSpan) -> None:
        cls._spans.append(span)
        if len(cls._spans) > 1000:
            cls._spans = cls._spans[-500:]

    @classmethod
    def get_recent_spans(cls, limit: int = 50) -> list[dict[str, Any]]:
        return [asdict(s) for s in reversed(cls._spans[-limit:])]

    @classmethod
    def clear(cls) -> None:
        cls._spans.clear()


@contextmanager
def trace_span(
    name: str,
    trace_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Generator[TraceSpan, None, None]:
    """
    Context manager to trace execution duration, parameters, and AI model tags.
    """
    t_id = trace_id or str(uuid.uuid4())
    s_id = str(uuid.uuid4())
    start = time.perf_counter()

    span = TraceSpan(
        trace_id=t_id,
        span_id=s_id,
        parent_span_id=None,
        name=name,
        start_time=start,
        attributes=attributes or {},
    )

    try:
        yield span
        span.status = "SUCCESS"
    except Exception as exc:
        span.status = "ERROR"
        span.attributes["error.type"] = type(exc).__name__
        span.attributes["error.message"] = str(exc)
        raise exc
    finally:
        end = time.perf_counter()
        span.end_time = end
        span.duration_ms = round((end - start) * 1000, 2)
        TelemetryStore.record_span(span)
        logger.info(
            "Telemetry Span: %s [%s] took %.2fms | attrs=%s",
            name,
            span.status,
            span.duration_ms,
            span.attributes,
        )
