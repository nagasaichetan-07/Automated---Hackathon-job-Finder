"""
Aegis — Pydantic v2 Domain Schemas

All domain entities, enumerations, and shared types used across the Aegis platform.
These schemas serve as the single source of truth for data validation and serialization.

NOTE: This file is a Phase 0 deliverable — schema definitions only.
      ORM models (SQLAlchemy) will be created in Phase 1 under storage/models/.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class EligibilityState(str, enum.Enum):
    """Eligibility evaluation outcome. UNKNOWN is mandatory when evidence is insufficient."""

    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class SourceHealth(str, enum.Enum):
    """Source health state, transitioned automatically based on run outcomes."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    BROKEN = "BROKEN"


class RepairState(str, enum.Enum):
    """Lifecycle state of a repair patch."""

    PROPOSED = "PROPOSED"
    TESTED = "TESTED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class OpportunityCategory(str, enum.Enum):
    """Type of opportunity."""

    JOB = "job"
    INTERNSHIP = "internship"
    HACKATHON = "hackathon"


class OpportunityMode(str, enum.Enum):
    """Participation mode."""

    REMOTE = "remote"
    ONSITE = "onsite"
    HYBRID = "hybrid"


class NotificationChannel(str, enum.Enum):
    """Notification delivery channel."""

    EMAIL = "email"
    TELEGRAM = "telegram"
    IN_APP = "in_app"


class NotificationType(str, enum.Enum):
    """Notification dispatch type."""

    IMMEDIATE = "immediate"
    DIGEST = "digest"


class FailureClass(str, enum.Enum):
    """Classification of connector failure for the repair pipeline."""

    SELECTOR_NOT_FOUND = "selector_not_found"
    SCHEMA_DRIFT = "schema_drift"
    ZERO_RECORDS = "zero_records"
    FIELD_QUALITY_DROP = "field_quality_drop"
    TIMEOUT_OR_RATE_LIMIT = "timeout_or_rate_limit"
    SOURCE_UNAVAILABLE = "source_unavailable"


class UserFeedback(str, enum.Enum):
    """User feedback action on a matched opportunity."""

    INTERESTED = "interested"
    DISMISSED = "dismissed"
    APPLIED = "applied"
    NOT_ELIGIBLE = "not_eligible"


class NotificationStatus(str, enum.Enum):
    """Notification delivery status."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class RepairRunOutcome(str, enum.Enum):
    """Outcome of a repair run."""

    SUCCESS = "success"
    FAILURE = "failure"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class RepairTriggerType(str, enum.Enum):
    """How a repair run was triggered."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"


# ---------------------------------------------------------------------------
# Domain Schemas
# ---------------------------------------------------------------------------


class SourceSchema(BaseModel):
    """A configured data source (API endpoint, web page, RSS feed)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., pattern=r"^(api|web|rss)$")
    url: str = Field(..., min_length=1)
    connector_class: str = Field(..., min_length=1)
    connector_config: dict = Field(default_factory=dict)
    cadence: str = Field(..., description="Cron expression for scheduling")
    enabled: bool = True
    health_state: SourceHealth = SourceHealth.HEALTHY
    access_notes: str | None = Field(default=None, description="Terms/access verification notes")
    consecutive_failures: int = Field(default=0, ge=0)
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class OpportunitySchema(BaseModel):
    """Canonical opportunity record. All connectors normalize into this schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    external_id: str = Field(..., description="Unique identifier from the source")
    title: str = Field(..., min_length=1)
    category: OpportunityCategory
    organizer: str | None = None
    url: str
    description: str | None = None
    registration_deadline: datetime | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    location: str | None = None
    mode: OpportunityMode | None = None
    eligibility_text: str | None = Field(default=None, description="Raw eligibility text from source")
    team_size_min: int | None = Field(default=None, ge=1)
    team_size_max: int | None = Field(default=None, ge=1)
    prize: str | None = None
    skills_themes: list[str] = Field(default_factory=list)
    evidence: dict = Field(
        default_factory=dict,
        description="Field-level evidence snippets mapping field name to source text",
    )
    content_hash: str | None = Field(default=None, description="Hash for dedup/idempotency")
    published_at: datetime | None = None
    collected_at: datetime
    created_at: datetime
    updated_at: datetime


class ProfileSchema(BaseModel):
    """User profile constructed from manual input and résumé extraction."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    education_level: str | None = None
    graduation_year: int | None = None
    branch: str | None = None
    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    opportunity_types: list[OpportunityCategory] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)
    resume_raw_text: str | None = None
    resume_extracted: dict | None = Field(default=None, description="Draft extracted fields from résumé")
    resume_confirmed: bool = Field(
        default=False, description="User has reviewed and confirmed extracted data"
    )
    resume_evidence: dict | None = Field(
        default=None, description="Per-field evidence and confidence values"
    )
    created_at: datetime
    updated_at: datetime


class EligibilityDecisionSchema(BaseModel):
    """Eligibility evaluation for an opportunity-profile pair."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    opportunity_id: UUID
    profile_id: UUID
    state: EligibilityState
    evidence: dict = Field(
        default_factory=dict,
        description="Rules checked and their results",
    )
    rule_results: dict = Field(
        default_factory=dict,
        description="Per-rule pass/fail detail",
    )
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    evaluated_at: datetime


class MatchScoreSchema(BaseModel):
    """Hybrid match score breakdown for an opportunity-profile pair."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    opportunity_id: UUID
    profile_id: UUID
    final_score: float = Field(..., ge=0.0, le=1.0)
    eligibility_score: float = Field(..., ge=0.0, le=1.0)
    feature_overlap_score: float = Field(..., ge=0.0, le=1.0)
    semantic_similarity_score: float = Field(..., ge=0.0, le=1.0)
    weights_used: dict = Field(
        default_factory=dict,
        description="Transparency: which weights produced this score",
    )
    score_breakdown: dict = Field(
        default_factory=dict,
        description="Full detail for audit",
    )
    explanation: str = Field(
        ...,
        description="Plain-language explanation grounded in stored facts",
    )
    user_feedback: UserFeedback | None = None
    scored_at: datetime


class NotificationSchema(BaseModel):
    """Notification event record with idempotency guarantee."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    profile_id: UUID
    opportunity_id: UUID
    channel: NotificationChannel
    notification_type: NotificationType
    idempotency_key: str = Field(
        ...,
        description="user + opportunity + meaningful version hash",
    )
    status: NotificationStatus = NotificationStatus.PENDING
    content: dict = Field(
        default_factory=dict,
        description="Rendered notification content",
    )
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime


class RepairRunSchema(BaseModel):
    """Audit record for a self-healing attempt on a source."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    trigger_type: RepairTriggerType
    failure_class: FailureClass
    error_summary: str | None = None
    diagnosis: dict = Field(
        default_factory=dict,
        description="Failure analysis details",
    )
    outcome: RepairRunOutcome | None = None
    started_at: datetime
    completed_at: datetime | None = None


class RepairPatchSchema(BaseModel):
    """A specific code patch proposed during a repair run."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repair_run_id: UUID
    state: RepairState
    diff_content: str = Field(..., description="Unified diff — never a full-file rewrite")
    target_file: str = Field(..., description="Connector file path")
    test_results: dict = Field(
        default_factory=dict,
        description="Pass/fail per test",
    )
    validation_results: dict = Field(
        default_factory=dict,
        description="Required fields met, no forbidden imports, etc.",
    )
    sandbox_passed: bool = False
    approved_by: str | None = Field(None, description="user_id or 'autonomous'")
    connector_version_before: str | None = None
    connector_version_after: str | None = None
    rejection_reason: str | None = None
    proposed_at: datetime
    tested_at: datetime | None = None
    promoted_at: datetime | None = None
    rolled_back_at: datetime | None = None


# ---------------------------------------------------------------------------
# Connector Interface Types (for documentation and type-checking)
# ---------------------------------------------------------------------------


class ConnectorMetadata(BaseModel):
    """Metadata returned alongside every connector fetch."""

    source_id: UUID
    connector_class: str
    fetch_timestamp: datetime
    content_hash: str
    record_count: int
    duration_ms: float
    success: bool
    error: str | None = None


class ConnectorHealthResult(BaseModel):
    """Result of a connector health check."""

    source_id: UUID
    health_state: SourceHealth
    consecutive_failures: int
    last_error: str | None = None
    checked_at: datetime
