"""
Aegis — Base Connector Interface Contract

Defines the invariant interface for all data source connectors (Greenhouse, Lever, RSS, Web).
Adheres strictly to the "Dumb Connector" principle: connectors only fetch, parse, and normalize
into OpportunitySchema. They never contain eligibility, matching, or ranking business logic.
"""

from __future__ import annotations

import hashlib
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from core.schemas.domain import OpportunitySchema


class TransientConnectorError(Exception):
    """Raised on recoverable network/rate-limit errors that Celery should retry with backoff."""


@dataclass(frozen=True)
class ConnectorMetadata:
    """Metadata describing a connector and its supported capabilities."""

    name: str
    source_type: str  # "api", "web", "rss"
    description: str
    version: str = "1.0.0"


@dataclass
class RawFetchResult:
    """Encapsulates the raw payload, parsed records, and cryptographic content hash."""

    raw_payload: str
    records: list[dict[str, Any]]
    content_hash: str
    record_count: int
    fetch_timestamp: datetime

    @classmethod
    def from_payload(
        cls,
        raw_payload: str,
        records: list[dict[str, Any]],
        fetch_timestamp: datetime | None = None,
    ) -> RawFetchResult:
        """Helper to construct fetch result with automatic SHA-256 hash calculation."""
        content_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
        return cls(
            raw_payload=raw_payload,
            records=records,
            content_hash=content_hash,
            record_count=len(records),
            fetch_timestamp=fetch_timestamp or datetime.now(UTC),
        )


@dataclass
class HealthCheckResult:
    """Result of a connector health probe against a target source."""

    healthy: bool
    latency_ms: float = 0.0
    status_code: int | None = None
    message: str | None = None


class BaseConnector(ABC):
    """
    Abstract Base Class for all Aegis connectors.
    Must be subclassed by Greenhouse, Lever, RSS, and Web connectors.
    """

    @property
    @abstractmethod
    def metadata(self) -> ConnectorMetadata:
        """Return connector metadata."""
        ...

    @abstractmethod
    async def fetch(self, config: dict[str, Any]) -> RawFetchResult:
        """
        Fetch raw records from the external source using the provided source configuration.
        Must return a RawFetchResult containing the raw payload and extracted record dictionaries.
        """
        ...

    @abstractmethod
    def normalize_raw(
        self,
        raw_item: dict[str, Any],
        source_id: uuid.UUID,
    ) -> OpportunitySchema:
        """
        Transform a single raw record into the canonical OpportunitySchema.
        Must attach field-level source evidence and compute content_hash for the item.
        """
        ...

    @abstractmethod
    async def health_check(self, config: dict[str, Any]) -> HealthCheckResult:
        """
        Perform a lightweight connectivity and schema check against the source.
        """
        ...
