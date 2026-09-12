# Aegis — PostgreSQL Data Model

## 1. Entity-Relationship Diagram

```mermaid
erDiagram
    Source ||--o{ Opportunity : "produces"
    Source ||--o{ RepairRun : "targets"
    Opportunity ||--o{ EligibilityDecision : "has"
    Opportunity ||--o{ MatchScore : "has"
    Opportunity ||--o{ Notification : "triggers"
    Profile ||--o{ EligibilityDecision : "evaluated_for"
    Profile ||--o{ MatchScore : "scored_for"
    Profile ||--o{ Notification : "sent_to"
    RepairRun ||--o{ RepairPatch : "generates"

    Source {
        uuid id PK
        varchar name
        varchar source_type "api | web | rss"
        varchar url
        varchar connector_class
        jsonb connector_config
        varchar cadence "cron expression"
        boolean enabled
        varchar health_state "HEALTHY | DEGRADED | BROKEN"
        text access_notes "terms/access verification"
        int consecutive_failures
        timestamp last_run_at
        timestamp last_success_at
        timestamp created_at
        timestamp updated_at
    }

    Opportunity {
        uuid id PK
        uuid source_id FK
        varchar external_id "unique per source"
        varchar title
        varchar category "job | internship | hackathon"
        varchar organizer
        text url
        text description
        timestamp registration_deadline
        timestamp start_date
        timestamp end_date
        varchar location
        varchar mode "remote | onsite | hybrid"
        text eligibility_text "raw eligibility from source"
        int team_size_min
        int team_size_max
        varchar prize
        jsonb skills_themes "array of strings"
        jsonb evidence "field-level evidence snippets"
        vector embedding "pgvector 384/768 dim"
        varchar content_hash "for dedup/idempotency"
        timestamp published_at
        timestamp collected_at
        timestamp created_at
        timestamp updated_at
    }

    Profile {
        uuid id PK
        uuid user_id FK "unique"
        varchar education_level
        int graduation_year
        varchar branch
        jsonb skills "normalized skill list"
        jsonb preferred_locations
        jsonb opportunity_types "job | internship | hackathon"
        jsonb interests
        jsonb constraints
        text resume_raw_text
        jsonb resume_extracted "draft extracted fields"
        boolean resume_confirmed "user reviewed and confirmed"
        jsonb resume_evidence "per-field evidence + confidence"
        vector embedding "pgvector"
        timestamp created_at
        timestamp updated_at
    }

    EligibilityDecision {
        uuid id PK
        uuid opportunity_id FK
        uuid profile_id FK
        varchar state "ELIGIBLE | INELIGIBLE | UNKNOWN"
        jsonb evidence "rules checked + results"
        jsonb rule_results "per-rule pass/fail detail"
        float confidence
        timestamp evaluated_at
    }

    MatchScore {
        uuid id PK
        uuid opportunity_id FK
        uuid profile_id FK
        float final_score
        float eligibility_score
        float feature_overlap_score
        float semantic_similarity_score
        jsonb weights_used "transparency: which weights produced this"
        jsonb score_breakdown "full detail for audit"
        text explanation "plain-language, fact-grounded"
        varchar user_feedback "interested | dismissed | applied | not_eligible"
        timestamp scored_at
    }

    Notification {
        uuid id PK
        uuid profile_id FK
        uuid opportunity_id FK
        varchar channel "email | telegram | in_app"
        varchar notification_type "immediate | digest"
        varchar idempotency_key "user + opportunity + version hash"
        varchar status "pending | sent | failed"
        jsonb content "rendered notification content"
        timestamp scheduled_at
        timestamp sent_at
        timestamp created_at
    }

    RepairRun {
        uuid id PK
        uuid source_id FK
        varchar trigger_type "automatic | manual"
        varchar failure_class "selector_not_found | schema_drift | zero_records | field_quality_drop | timeout_or_rate_limit | source_unavailable"
        text error_summary
        jsonb diagnosis "failure analysis details"
        varchar outcome "success | failure | rejected | rolled_back"
        timestamp started_at
        timestamp completed_at
    }

    RepairPatch {
        uuid id PK
        uuid repair_run_id FK
        varchar state "PROPOSED | TESTED | PROMOTED | REJECTED"
        text diff_content "unified diff"
        varchar target_file "connector file path"
        jsonb test_results "pass/fail per test"
        jsonb validation_results "required fields met, no forbidden imports, etc."
        boolean sandbox_passed
        varchar approved_by "user_id or 'autonomous'"
        varchar connector_version_before
        varchar connector_version_after
        text rejection_reason
        timestamp proposed_at
        timestamp tested_at
        timestamp promoted_at
        timestamp rolled_back_at
    }
```

## 2. Entity Descriptions

### Source
Represents a configured data source (API endpoint, web page, RSS feed). Stores connector configuration, scheduling cadence, and health state. Health transitions automatically based on consecutive run outcomes.

**Unique constraint**: `(source_type, url)` — prevents duplicate source registrations.

### Opportunity
The canonical opportunity record. All connectors normalize their output into this schema. Contains the pgvector embedding for semantic search.

**Unique constraint**: `(source_id, external_id)` — prevents duplicate opportunities per source.
**Index**: GiST index on `embedding` for pgvector similarity queries.

### Profile
User profile constructed from manual input and résumé extraction. The `resume_confirmed` flag gates whether extracted data is treated as authoritative. Contains a pgvector embedding for matching.

**Unique constraint**: `(user_id)` — one profile per user.

### EligibilityDecision
Records the eligibility evaluation of a specific opportunity for a specific profile. State is always ELIGIBLE, INELIGIBLE, or UNKNOWN — never inferred without evidence.

**Unique constraint**: `(opportunity_id, profile_id)` — one decision per opportunity-profile pair (latest wins, history in audit log).

### MatchScore
Stores the full hybrid scoring breakdown for an opportunity-profile pair. Includes the plain-language explanation and optional user feedback.

**Unique constraint**: `(opportunity_id, profile_id)` — one score per pair.

### Notification
Tracks every notification event. The `idempotency_key` prevents duplicate notifications for the same unchanged opportunity.

**Unique constraint**: `(idempotency_key)` — absolute dedup guarantee.

### RepairRun
Audit record for a single self-healing attempt on a source. Captures the failure classification, diagnosis, and final outcome.

### RepairPatch
The specific code patch proposed during a repair run. Tracks its lifecycle through PROPOSED → TESTED → PROMOTED/REJECTED, with full test and validation results.

## 3. Enumerations

| Enum | Values | Usage |
|------|--------|-------|
| `EligibilityState` | `ELIGIBLE`, `INELIGIBLE`, `UNKNOWN` | EligibilityDecision.state |
| `SourceHealth` | `HEALTHY`, `DEGRADED`, `BROKEN` | Source.health_state |
| `RepairState` | `PROPOSED`, `TESTED`, `PROMOTED`, `REJECTED` | RepairPatch.state |
| `OpportunityCategory` | `job`, `internship`, `hackathon` | Opportunity.category |
| `OpportunityMode` | `remote`, `onsite`, `hybrid` | Opportunity.mode |
| `NotificationChannel` | `email`, `telegram`, `in_app` | Notification.channel |
| `NotificationType` | `immediate`, `digest` | Notification.notification_type |
| `FailureClass` | `selector_not_found`, `schema_drift`, `zero_records`, `field_quality_drop`, `timeout_or_rate_limit`, `source_unavailable` | RepairRun.failure_class |
| `UserFeedback` | `interested`, `dismissed`, `applied`, `not_eligible` | MatchScore.user_feedback |

## 4. Key Design Decisions

1. **pgvector for embeddings**: Embeddings stored alongside relational data in PostgreSQL, avoiding a separate vector database. Uses GiST indexing for approximate nearest neighbor search.

2. **Content hashing for idempotency**: `Opportunity.content_hash` and `Notification.idempotency_key` enforce that re-crawls and re-notifications are no-ops for unchanged data.

3. **Evidence-first design**: Every AI-derived field (eligibility, match score, explanation) carries explicit evidence references. No unexplained AI output.

4. **Audit trail for repairs**: `RepairRun` + `RepairPatch` provide a complete, queryable audit trail for every self-healing attempt, successful or not.

5. **All timestamps timezone-aware, stored in UTC**: Consistent across all entities.
