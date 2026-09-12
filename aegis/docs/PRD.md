# Aegis — Product Requirements Document

## 1. Product Summary

**Aegis** is an AI-integrated, autonomously operating opportunity-intelligence platform for students. It continuously collects jobs, internships, and hackathons from multiple sources; evaluates eligibility; ranks and matches opportunities to a student's profile; delivers deduplicated notifications; and self-heals its own data pipeline when sources break — all without manual human triggering.

---

## 2. MVP Scope (Definition-of-Done)

Derived directly from Section 2.3 of the Build Directive.

### MVP-1: Profile & Résumé Intelligence
**Capability**: A user can create a profile, upload a résumé, and see it converted into a structured, reviewable profile.

**Acceptance Criteria**:
- AC-1.1: User can register and create a profile with education, year, branch, skills, locations, opportunity types, interests, and constraints.
- AC-1.2: User can upload a résumé (PDF). The system extracts structured data deterministically first, then optionally refines with an LLM.
- AC-1.3: Every extracted field carries source evidence and a confidence value.
- AC-1.4: Extracted data is presented as a DRAFT. It becomes authoritative only after user review and confirmation.
- AC-1.5: Malicious/injected content in résumé text does not alter system or agent behavior (proven by test).
- AC-1.6: Invalid file types and oversized uploads are rejected with clear error messages.

### MVP-2: Autonomous Multi-Source Collection
**Capability**: The system autonomously collects jobs, internships, and hackathons from at least two API-based sources and at least one web-extraction source on its own schedule.

**Acceptance Criteria**:
- AC-2.1: At least two API-based connectors (Greenhouse, Lever) produce valid, schema-conformant opportunity records from fixtures.
- AC-2.2: At least one web-extraction connector (Crawl4AI/Playwright) parses hackathon/opportunity pages into the same canonical Opportunity schema.
- AC-2.3: Celery Beat runs collection on configurable per-source cadences with zero manual trigger.
- AC-2.4: Re-running the same collection job does not create duplicate raw snapshots (idempotency).
- AC-2.5: Raw responses are stored with content hashes and timestamps for full auditability.
- AC-2.6: Source health transitions (HEALTHY → DEGRADED → BROKEN) are tracked automatically.
- AC-2.7: All CI tests run from recorded fixtures — no live website dependency.

### MVP-3: Eligibility, Matching & Ranking
**Capability**: Every opportunity shown to the user has an eligibility state (ELIGIBLE / INELIGIBLE / UNKNOWN) with evidence, and a ranked match score with an explanation grounded only in stored facts.

**Acceptance Criteria**:
- AC-3.1: Hard eligibility constraints (degree, year, branch, team size, location, deadline) are evaluated deterministically — no LLM in the critical disqualification path.
- AC-3.2: Eligibility output is always one of ELIGIBLE, INELIGIBLE, or UNKNOWN with supporting evidence.
- AC-3.3: UNKNOWN is preserved when evidence is insufficient — never silently resolved to ELIGIBLE.
- AC-3.4: Hard disqualifications always override high similarity scores.
- AC-3.5: Match score is a transparent hybrid: hard eligibility + structured feature overlap + semantic similarity (pgvector), with configurable weights.
- AC-3.6: Full score breakdown (not just final number) is stored and displayable.
- AC-3.7: Every explanation is traceable to specific stored facts — no invented reasons.

### MVP-4: Autonomous Notifications
**Capability**: The user receives deduplicated notifications (email at minimum) without manual triggering.

**Acceptance Criteria**:
- AC-4.1: Email notifications are sent automatically for new high-value matches (immediate alert) and as daily digests.
- AC-4.2: A stable idempotency key (user + opportunity + meaningful-version) prevents duplicate notifications.
- AC-4.3: Re-notification occurs only on meaningful field changes, never on no-op re-crawls.
- AC-4.4: Quiet hours are respected.
- AC-4.5: Every notification includes: title, category, match score, eligibility state, deadline, explanation, source URL.
- AC-4.6: Tests use a fake email backend — no real credentials required in CI.

### MVP-5: Self-Healing Connector System
**Capability**: A deliberately broken data source is detected, diagnosed, patched, tested in a sandbox, and — after passing validation and (in default mode) human approval — deployed and confirmed working, with rollback proven to work.

**Acceptance Criteria**:
- AC-5.1: Connector anomalies are detected automatically from health/metrics data.
- AC-5.2: Failures are classified (selector_not_found, schema_drift, zero_records, field_quality_drop, timeout_or_rate_limit, source_unavailable).
- AC-5.3: Repair agent receives only scoped inputs — never broader repo access or secrets.
- AC-5.4: Patches are minimal unified diffs, never full-file rewrites.
- AC-5.5: Patches are applied only in an isolated sandbox/Git worktree.
- AC-5.6: Regression tests gate promotion eligibility.
- AC-5.7: Default mode requires human approval before merge; autonomous promotion is behind an explicit, default-OFF flag.
- AC-5.8: Post-deployment metric degradation triggers automatic rollback.
- AC-5.9: A kill switch immediately disables all autonomous repair.
- AC-5.10: Full audit trail for every repair attempt (accepted or rejected).

### MVP-6: Evaluation & Observability
**Capability**: An evaluation dashboard shows real, reproducible metrics (not vanity numbers) for extraction accuracy, ranking quality, and repair reliability.

**Acceptance Criteria**:
- AC-6.1: A labeled benchmark dataset is versioned in the repository.
- AC-6.2: Metrics include extraction precision/recall, eligibility accuracy, ranking precision@5/@10, duplicate-notification rate, source success rate, repair acceptance/rollback rates, MTTR.
- AC-6.3: All metrics are reproducible by re-running the evaluation suite locally.
- AC-6.4: System Health dashboard shows real, live-computed data — no hardcoded numbers.
- AC-6.5: Chaos tests cover: selector disappears, empty result, malformed JSON, API timeout, HTTP 429, duplicate opportunity, changed date format, injected malicious instruction.

### MVP-7: Security & Deployment
**Capability**: A security pass has been completed with no critical findings, and the system is deployed behind authentication with secrets externalized.

**Acceptance Criteria**:
- AC-7.1: No hardcoded secrets in source or config.
- AC-7.2: SSRF protection on all URL-fetching paths (block localhost, private IPs, cloud metadata).
- AC-7.3: Authentication and authorization on API and dashboard.
- AC-7.4: PostgreSQL and Redis are not publicly exposed.
- AC-7.5: Health/readiness checks pass after deployment.
- AC-7.6: Database backup strategy documented and in place.

---

## 3. Post-MVP Scope

The following are explicitly out of MVP scope but anticipated for future development:

- **Fully autonomous repair promotion** — enabled only after Phase 8 evaluation proves reliability, controlled by an explicit feature flag.
- **Additional notification channels** — Telegram Bot API, in-app WebSocket/SSE push (email is MVP-mandatory).
- **Multi-user / multi-tenant** — MVP targets single-user operation.
- **Advanced ML feedback loop** — using user feedback (interested, dismissed, applied, not_eligible) to retrain or fine-tune ranking.
- **Additional source connectors** — beyond the initial Greenhouse, Lever, RSS, and web connectors.
- **Mobile-native applications** — dashboard is responsive web; no native mobile app in MVP.

---

## 4. User Roles

| Role | Permissions |
|------|------------|
| **Student (Primary User)** | Create/edit profile, upload résumé, view feed, save/dismiss opportunities, configure notification preferences, manage sources |
| **Administrator** | All student permissions + view source access notes, approve/reject repair patches, toggle kill switch, view system health |

---

## 5. Non-Functional Requirements

- **Autonomy**: The system operates without human triggering for collection, extraction, matching, ranking, deduplication, and notification.
- **Idempotency**: All scheduled/background jobs are idempotent — no duplicate records or notifications on re-run.
- **Auditability**: Every AI-derived decision carries evidence references and confidence values.
- **Safety**: AI-generated code changes are diff-only, sandboxed, tested, and approval-gated before production promotion.
- **Security**: SSRF hardening, prompt-injection resistance, secret externalization, authentication/authorization.
- **Testability**: All CI tests run from fixtures — never depending on live external services.
