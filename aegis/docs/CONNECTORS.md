# Aegis — Connector Interface Contract

## 1. Overview

Every data source connector in Aegis implements a uniform interface. This contract ensures that:

1. **Connectors are interchangeable** — the pipeline doesn't know or care whether data came from an API or a web page.
2. **Connectors are "dumb"** — they return raw/structured data only. All business logic (eligibility, matching, ranking) lives in `opportunity/`.
3. **Self-repair is safe** — the repair agent can be scoped to a single connector file without risk of touching business logic.

## 2. Interface Definition

Every connector class MUST implement the following three methods:

### `fetch() -> tuple[list[dict], ConnectorMetadata]`

**Purpose**: Retrieve raw data from the source.

**Behavior**:
- Returns a list of raw opportunity records (as dicts) and a `ConnectorMetadata` object.
- Must be **idempotent** — re-running with the same source state produces the same output without side effects.
- Must store a raw snapshot with content hash and timestamp for auditability.
- Must handle network errors gracefully (timeouts, rate limits) and report them in metadata.
- Must respect rate limits and backoff policies.
- Must **never** bypass CAPTCHAs, logins, paywalls, or anti-bot protections.
- Must **never** fetch URLs outside the configured source domain without explicit allowlist membership.

**Parameters** (injected via constructor or config):
- `source: SourceSchema` — the source configuration including URL, connector config, etc.

**Returns**:
- `list[dict]` — raw records in source-native format.
- `ConnectorMetadata` — fetch timestamp, content hash, record count, duration, success/failure.

**Error handling**:
- On transient failure: raise a retryable exception (Celery will retry with exponential backoff).
- On permanent failure: return empty list with `success=False` and error description in metadata.

---

### `normalize_raw(raw_records: list[dict]) -> list[OpportunitySchema]`

**Purpose**: Transform raw source-native records into the canonical `OpportunitySchema`.

**Behavior**:
- Maps source-specific fields to canonical fields.
- Normalizes dates to timezone-aware UTC.
- Computes a `content_hash` for deduplication.
- Sets `collected_at` to the current timestamp.
- Populates the `evidence` dict with field-level source text snippets.
- For any field that cannot be confidently determined, stores `None` / `UNKNOWN` — **never invents values**.
- Must be a **pure function** — no network calls, no side effects.

**Returns**:
- `list[OpportunitySchema]` — normalized, schema-valid opportunity records.

---

### `health_check() -> ConnectorHealthResult`

**Purpose**: Assess the current health of the source.

**Behavior**:
- Performs a lightweight connectivity/validity check (e.g., HEAD request, fetch first page).
- Returns the current health state based on recent run history:
  - `HEALTHY` — last N runs all succeeded.
  - `DEGRADED` — some recent failures but still partially functional (e.g., reduced record count, intermittent errors).
  - `BROKEN` — consecutive failures exceed threshold.
- Must not perform a full data fetch — this is a probe, not a collection run.
- Must record the check result for monitoring.

**Returns**:
- `ConnectorHealthResult` — health state, consecutive failure count, last error, check timestamp.

---

## 3. Required Metadata Fields

Every connector must provide these metadata fields on every fetch:

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | UUID | The source this fetch belongs to |
| `connector_class` | str | Fully qualified class name of the connector |
| `fetch_timestamp` | datetime (UTC) | When the fetch started |
| `content_hash` | str | SHA-256 hash of the raw response body/payload |
| `record_count` | int | Number of records returned |
| `duration_ms` | float | Wall-clock fetch duration in milliseconds |
| `success` | bool | Whether the fetch completed without error |
| `error` | str or None | Error description if `success` is False |

## 4. Connector Configuration

Each connector receives its configuration via the `Source.connector_config` JSON field. This allows per-source customization without code changes.

Example configurations:

```json
// Greenhouse
{
  "board_token": "example_company",
  "base_url": "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
}

// Lever
{
  "company_identifier": "example-company",
  "base_url": "https://api.lever.co/v0/postings/{company_identifier}"
}

// RSS
{
  "feed_url": "https://example.com/opportunities.rss"
}

// Web (Crawl4AI/Playwright)
{
  "target_url": "https://example.com/hackathons",
  "selectors": {
    "listing_container": ".hackathon-list",
    "item": ".hackathon-card",
    "title": "h3.title",
    "deadline": ".deadline-date",
    "url": "a.detail-link"
  },
  "domain_allowlist": ["example.com"]
}
```

## 5. Health State Transitions

```mermaid
statechart-v2
    [*] --> HEALTHY
    HEALTHY --> DEGRADED : intermittent failure
    HEALTHY --> BROKEN : N consecutive failures
    DEGRADED --> HEALTHY : successful run
    DEGRADED --> BROKEN : continued failures
    BROKEN --> DEGRADED : successful run after repair
    BROKEN --> HEALTHY : N consecutive successes
```

Default thresholds (configurable):
- `HEALTHY → DEGRADED`: 1 failure after a run of successes
- `DEGRADED → BROKEN`: 3 consecutive failures
- `BROKEN → HEALTHY`: 3 consecutive successes after repair

## 6. Security Constraints

- **SSRF Protection**: Every URL fetched must be validated against SSRF rules — block `localhost`, `127.0.0.1`, `::1`, private IP ranges (`10.x`, `172.16-31.x`, `192.168.x`), and cloud metadata endpoints (`169.254.169.254`).
- **Domain Allowlist**: Web connectors must only fetch URLs within their configured `domain_allowlist`.
- **Rate Limiting**: Connectors must respect source-configured rate limits and implement exponential backoff.
- **No Credential Leakage**: Connector configs may contain tokens but these are never logged, never passed to AI agents, and never committed to source control.
- **Content is Untrusted**: All fetched content is treated as untrusted input — instructions embedded in page text must never be treated as system instructions by any AI component.

## 7. Connector Isolation Principle

```
connectors/          →     normalization/     →     opportunity/
(raw data only)            (canonical schema)       (business logic)

  ↑ Repair agent                                    ✗ Repair agent
    CAN touch this                                    CANNOT touch this
```

The repair agent's scope is limited to files within `connectors/` and their associated test fixtures. It must never modify:
- Normalization logic
- Eligibility rules
- Matching/ranking algorithms
- Notification logic
- API routes
- Database models
