# Aegis — Testing Strategy

## 1. Overview

Testing in Aegis follows a layered approach: unit tests, integration tests, regression tests, chaos tests, and security tests. All CI tests run from saved fixtures — **no test may depend on a live website being reachable or unchanged**.

**Test framework**: Pytest (backend), Playwright test runner (browser/E2E).

---

## 2. Test Categories

### 2.1 Unit Tests (`tests/unit/`)

Fast, isolated tests for individual functions and classes. Mock all external dependencies.

### 2.2 Integration Tests (`tests/integration/`)

Tests that exercise multiple components together (e.g., connector → normalization → storage). Use a real test database (PostgreSQL with pgvector) but no live external services.

### 2.3 Fixture-Based Regression Tests (`tests/regression/`)

Tests that run against a frozen set of saved API responses, HTML pages, and expected outputs. These are the primary correctness guarantee and must never be skipped.

### 2.4 Chaos Tests (`tests/chaos/`)

Deliberately inject failures to verify resilience:
- Selector disappears from page
- Page returns empty result
- Malformed JSON response
- API timeout
- HTTP 429 (rate limit)
- Duplicated opportunity
- Changed date format
- Page containing injected malicious instruction aimed at the model

### 2.5 Security Tests (`tests/security/`)

- Prompt injection resistance (scraped content and résumé text)
- SSRF protection (blocked destinations)
- Repair patch validation (forbidden imports, out-of-scope changes)
- Credential non-exposure in logs and AI agent inputs

### 2.6 Test Fixtures (`tests/fixtures/`)

Saved responses from external sources. These are versioned in the repository and are the sole basis for regression testing. Live-source tests are **explicitly opt-in** and never required for CI.

---

## 3. Acceptance Criteria by MVP Capability

### MVP-1: Profile & Résumé Intelligence

| Test ID | Description | Type |
|---------|-------------|------|
| T-1.1 | Upload limits and MIME checks reject invalid files (wrong type, oversized) | Unit |
| T-1.2 | Deterministic PDF text extraction runs before any LLM step | Integration |
| T-1.3 | All LLM extraction output is schema-validated before storage | Unit |
| T-1.4 | Profile facts are never marked authoritative without `resume_confirmed=True` | Unit |
| T-1.5 | Résumé text containing prompt-injection instructions is neutralized — system behavior unchanged | Security |
| T-1.6 | Malformed PDFs are handled gracefully (no crash, clear error) | Unit |
| T-1.7 | Empty résumés produce empty/null fields, not fabricated data | Unit |
| T-1.8 | Conflicting dates in résumé are flagged, not silently resolved | Unit |
| T-1.9 | Duplicate skills are deduplicated and normalized (e.g., JS → JavaScript) | Unit |

### MVP-2: Autonomous Multi-Source Collection

| Test ID | Description | Type |
|---------|-------------|------|
| T-2.1 | Greenhouse fixture produces valid, schema-conformant opportunity records | Regression |
| T-2.2 | Lever fixture produces valid, schema-conformant opportunity records | Regression |
| T-2.3 | Re-running collection does not create duplicate raw snapshots | Integration |
| T-2.4 | Retry/backoff behavior is demonstrated (mock transient failure) | Unit |
| T-2.5 | Source health transitions HEALTHY→DEGRADED→BROKEN based on run outcomes | Unit |
| T-2.6 | RSS connector parses feed fixture correctly | Regression |
| T-2.7 | Content hash is stable across identical fetches | Unit |
| T-2.8 | Source-run metrics (success/failure, record count, duration) are recorded | Integration |

### MVP-3: Eligibility, Matching & Ranking

| Test ID | Description | Type |
|---------|-------------|------|
| T-3.1 | Hard eligibility constraints are fully deterministic — no LLM call in disqualification path | Unit |
| T-3.2 | UNKNOWN is preserved when evidence is insufficient | Unit |
| T-3.3 | Hard disqualification overrides high similarity score | Unit |
| T-3.4 | pgvector similarity queries return correctly on test embeddings | Integration |
| T-3.5 | Score breakdown is stored and retrievable, not just final number | Integration |
| T-3.6 | Every generated explanation traces to specific stored facts | Unit |
| T-3.7 | Synthetic profile/opportunity pairs with known expected ranking order verify ranking correctness | Regression |

### MVP-4: Autonomous Notifications

| Test ID | Description | Type |
|---------|-------------|------|
| T-4.1 | Repeated scheduler runs never produce duplicate alert for unchanged opportunity | Integration |
| T-4.2 | Daily digest correctly groups multiple opportunities | Unit |
| T-4.3 | Quiet hours are respected | Unit |
| T-4.4 | Fake email backend passes in CI without external credentials | Integration |
| T-4.5 | Notification includes all required fields (title, category, score, eligibility, deadline, explanation, URL) | Unit |
| T-4.6 | Re-notification triggers only on meaningful field changes | Unit |

### MVP-5: Self-Healing Connector System

| Test ID | Description | Type |
|---------|-------------|------|
| T-5.1 | Synthetic broken fixture triggers failure detection | Integration |
| T-5.2 | Repair agent produces minimal diff, not wholesale rewrite | Unit |
| T-5.3 | Patch applies only inside isolated worktree | Integration |
| T-5.4 | Regression tests gate promotion eligibility | Integration |
| T-5.5 | Rejected patch never reaches production branch | Integration |
| T-5.6 | Rollback restores last known-good connector version | Integration |
| T-5.7 | Full audit trail exists for every repair attempt | Integration |
| T-5.8 | Kill switch immediately stops all repair activity | Unit |
| T-5.9 | Repair agent never receives credentials or secrets | Security |
| T-5.10 | Page with adversarial instructions does not produce malicious patch | Security |

### MVP-6: Evaluation & Observability

| Test ID | Description | Type |
|---------|-------------|------|
| T-6.1 | Benchmark dataset is loadable and parseable | Unit |
| T-6.2 | Evaluation suite produces all required metrics | Integration |
| T-6.3 | Chaos tests all pass (selector gone, empty result, malformed JSON, etc.) | Chaos |
| T-6.4 | System Health dashboard data matches computed metrics | Integration |

### MVP-7: Security & Deployment

| Test ID | Description | Type |
|---------|-------------|------|
| T-7.1 | No hardcoded secrets in source (automated scan) | Security |
| T-7.2 | SSRF blocklist rejects localhost, private IPs, metadata endpoints | Security |
| T-7.3 | Health checks pass when services are up, fail correctly when down | Integration |
| T-7.4 | Docker Compose stack starts successfully from clean state | Integration |

---

## 4. CI/CD Testing Requirements

- **Every push** triggers: lint (Ruff/Black), type-check (mypy/pyright), unit tests, regression tests.
- **All tests must pass** before any merge to main.
- **No test may require** live external service access, real email credentials, or internet connectivity.
- **Fixture tests are the primary gate** — never rely solely on live websites for regression checking.
- **Live-source tests** (if any) are explicitly opt-in via environment variable or test marker, and never block CI.

## 5. Test Data Management

- Fixtures are versioned in `tests/fixtures/` and never modified without a corresponding test update.
- A frozen regression fixture set is maintained alongside the benchmark dataset.
- Test databases are created fresh for each test run (or test session) using Alembic migrations.
