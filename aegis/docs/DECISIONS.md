# Aegis — Architecture Decision Records (ADRs)

This document records the architectural and design decisions made throughout the lifecycle of the Aegis project, including rationale, trade-offs, and assumptions.

---

## ADR-001: Core Technology Stack Selection
- **Status**: Accepted
- **Context**: Aegis requires high-throughput asynchronous collection, vector-based semantic retrieval, robust relational modeling, and autonomous background processing.
- **Decision**: Lock stack to:
  - Backend: Python 3.11+, FastAPI (typed Pydantic v2 schemas).
  - Database: PostgreSQL 15+ with `pgvector` extension (relational and vector data co-located).
  - Queue / Scheduler: Redis + Celery + Celery Beat.
  - Web Crawling: Crawl4AI + Playwright (fallback for sources without public APIs/feeds).
  - Embeddings: Sentence Transformers (local open-source embeddings).
  - Local LLM: Ollama (Gemma / Qwen / DeepSeek) for zero-cost / local developer environments.
  - Frontend: React + TypeScript.
- **Consequences**: No external vector DB (Pinecone, Qdrant, Milvus) allowed. Single primary database reduces operational complexity and enables transactional consistency between opportunities and vector embeddings.

---

## ADR-002: Connector Isolation & "Dumb Connector" Principle
- **Status**: Accepted
- **Context**: Self-healing code repair modifies connector logic. If connectors contain business logic, an AI repair agent could corrupt scoring or eligibility rules.
- **Decision**: Connectors must be strictly "dumb":
  - They only implement `fetch()`, `normalize_raw()`, and `health_check()`.
  - They return raw/source-structured data and metadata.
  - No business logic (eligibility, matching, ranking, deduplication) is permitted in `connectors/`.
  - Data flows strictly one-way: `connectors/` -> `normalization/` -> `opportunity/`.
  - Circular dependencies between `connectors/` and `opportunity/` are forbidden.
- **Consequences**: Repair agents are strictly confined to touching single connector files under `connectors/` and cannot alter eligibility or ranking logic.

---

## ADR-003: Tri-State Eligibility & Mandatory UNKNOWN State
- **Status**: Accepted
- **Context**: LLMs tend to make binary assumptions when evidence is missing or ambiguous.
- **Decision**: Eligibility outputs are strictly tri-state:
  - `ELIGIBLE`: Hard stated requirements explicitly met.
  - `INELIGIBLE`: Hard exclusion criteria explicitly violated.
  - `UNKNOWN`: Evidence is absent or ambiguous.
  - If evidence is insufficient, state MUST remain `UNKNOWN` — it is never silently inferred as `ELIGIBLE` or `INELIGIBLE`.
  - Hard exclusions always dominate and override semantic similarity.
- **Consequences**: Prevents students from being falsely disqualified or falsely promised eligibility on ambiguous data.

---

## ADR-004: Two-Stage Résumé & Web Extraction Hierarchy
- **Status**: Accepted
- **Context**: Processing raw documents directly with LLMs is expensive, nondeterministic, and susceptible to prompt injection.
- **Decision**:
  - Deterministic text extraction (pdfminer/pypdf for résumé; JSON-LD / stable CSS selectors for web) must run FIRST.
  - LLM-assisted structuring runs ONLY as a secondary pass on the extracted text.
  - LLM output must be schema-validated before persistence.
  - Extracted résumé data remains a `DRAFT` until the user explicitly reviews and confirms it.
- **Consequences**: Lower token costs, consistent parsing, prompt injection resilience, and authoritative user control over profile data.

---

## ADR-005: Repair Safety: Isolated Sandbox, Diff-Only, and Approval Gate
- **Status**: Accepted
- **Context**: AI-generated code changes deployed to production present severe security and stability risks.
- **Decision**:
  - Direct overwriting of working branch files is prohibited.
  - Patches must be minimal unified diffs (<= 200 lines).
  - Patches execute only inside isolated Git worktrees with regression test execution.
  - Promotion is human-approval-gated by default. Fully autonomous promotion is gated behind an explicit `AEGIS_AUTO_PROMOTE_REPAIRS=false` flag and can only be enabled after Phase 8 evaluation metrics justify it.
  - Mandatory rollback mechanism tracks previous connector versions.
  - Global kill switch (`AEGIS_REPAIR_ENABLED`) halts all self-healing loops immediately.
- **Consequences**: Guarantees zero unverified code execution in production while preserving an audit record of all repair attempts.

---

## ADR-006: Notification Deduplication via Stable Idempotency Keys
- **Status**: Accepted
- **Context**: Background scheduled jobs running periodically must never flood users with repeated alerts for unchanged opportunities.
- **Decision**:
  - Notifications compute an idempotency key: `SHA256(user_id + opportunity_id + meaningful_version_hash)`.
  - A unique database constraint on `idempotency_key` guarantees at-most-once notification dispatch per version.
  - Re-crawls that do not change meaningful fields (e.g. deadline, title, eligibility) do not trigger new notifications.
- **Consequences**: Predictable alert delivery, zero alert spam on routine scheduler sweeps.
