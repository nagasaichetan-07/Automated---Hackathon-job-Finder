# Aegis — Security Model: Repair-Safety

## 1. Overview

The self-healing connector system is Aegis's most security-sensitive feature. An AI agent proposes code changes to fix broken data connectors. This document specifies every safeguard that prevents a repair from causing harm.

**Cardinal rule**: An LLM must never directly overwrite production source files. All AI-proposed changes are represented as a versioned diff/patch, applied only inside an isolated sandbox, tested, and promoted only after passing validation.

---

## 2. Repair Pipeline Security Controls

### 2.1 Sandbox Isolation

- Every repair patch is applied in an **isolated Git worktree**, completely separate from the main working branch.
- The sandbox has:
  - ✅ Read access to the target connector file and its test fixtures
  - ✅ A copy of the regression test suite
  - ❌ No access to production database credentials
  - ❌ No access to environment secrets
  - ❌ No network access to production services
  - ❌ No ability to modify files outside the connector directory
- The sandbox is **ephemeral** — created for each repair attempt and destroyed after validation, regardless of outcome.

### 2.2 Diff-Only Patches

- The repair agent produces a **minimal unified diff**, never a full-file rewrite.
- Diffs are validated before application:
  - Only the target connector file may be modified.
  - No changes to files outside `connectors/` and `tests/fixtures/`.
  - No new file creations outside the target directory.
  - Maximum diff size limit enforced (configurable, default: 200 lines).

### 2.3 Mandatory Test Gate

- After the patch is applied in the sandbox, the following tests run automatically:
  1. **Unit tests** for the target connector.
  2. **Regression tests** against the full fixture set.
  3. **Schema validation** — extracted records must conform to `OpportunitySchema`.
- **All tests must pass** for the patch to be eligible for promotion.
- A single test failure results in automatic rejection.

### 2.4 Validation Threshold

Before a patch is eligible for promotion, a validation step checks:

| Check | Requirement |
|-------|-------------|
| Tests pass | All unit + regression tests green |
| Required fields extracted | Core fields (title, url, external_id) present in ≥ 90% of fixture records |
| No unrelated files changed | Diff touches only the target connector and its fixtures |
| No forbidden imports | No `os.system`, `subprocess`, `exec`, `eval`, `__import__`, `importlib` |
| No shell commands | No inline shell execution |
| No secrets introduced | No hardcoded tokens, passwords, or API keys in the diff |
| No network calls added | No new HTTP/socket calls outside the connector's existing fetch pattern |
| Diff size within limit | Total lines changed ≤ configured maximum |

### 2.5 Approval Step

- **Default mode**: Every validated patch enters an **approval queue** visible to administrators.
  - The administrator sees: the diff, test results, validation results, failure diagnosis, and before/after extraction comparison.
  - The administrator can: **approve** (promote to production), **reject** (with reason), or **request revision**.
- **Autonomous mode**: A separate, explicitly-named feature flag (`AEGIS_AUTO_PROMOTE_REPAIRS`) controls fully autonomous promotion.
  - This flag **defaults to OFF**.
  - It should only be enabled after Phase 8 evaluation demonstrates that the repair pipeline is reliable (low rollback rate, high acceptance rate).
  - Even with autonomous promotion enabled, all validation checks still run — the flag only skips the human approval step.

### 2.6 Rollback

- Every promoted patch retains the previous connector version.
- **Automatic rollback** triggers if post-deployment metrics degrade:
  - Record count drops below threshold vs. last known-good run.
  - Error rate exceeds threshold in the first N runs after promotion.
  - Health state transitions to BROKEN within the monitoring window.
- **Manual rollback** is always available via the dashboard or API.
- Rollback restores the last known-good connector version immediately.
- The rolled-back patch is marked as `ROLLED_BACK` in the audit trail.

### 2.7 Kill Switch

- A global kill switch (`AEGIS_REPAIR_ENABLED`) **immediately disables all autonomous repair activity**.
- When disabled:
  - No new repair runs are initiated.
  - In-progress repair runs are cancelled.
  - No patches are promoted (even manually queued ones are paused).
  - Source monitoring continues — failures are still detected and logged.
- The kill switch is accessible via:
  - Environment variable
  - Admin API endpoint
  - Dashboard toggle

---

## 3. Repair Agent Input Scoping

The repair agent receives **only**:

| Input | Source |
|-------|--------|
| Connector source code | Single file from `connectors/` |
| Test fixture | Saved HTML/JSON snapshot from `tests/fixtures/` |
| Sanitized page snapshot | Recent page content (treated as **untrusted**) |
| Error message | Recent failure stack trace/error |
| Canonical schema | `OpportunitySchema` definition |
| Regression tests | Test files for the target connector |

The repair agent **never** receives:
- Database credentials or connection strings
- API keys or OAuth tokens
- Environment variable values
- Files from outside `connectors/` and `tests/`
- Access to the production database
- Ability to execute arbitrary shell commands

---

## 4. Audit Trail

Every repair attempt is fully auditable:

| Record | Contents |
|--------|----------|
| `RepairRun` | Source, trigger type, failure classification, diagnosis, outcome, timestamps |
| `RepairPatch` | Diff content, target file, test results, validation results, sandbox outcome, approval status, approver, version info, rejection reason if applicable |

Records are retained indefinitely. Both accepted and rejected patches are stored for post-hoc analysis.

---

## 5. Prompt Injection Defense in Repair

Scraped page content processed by the repair agent may contain adversarial text designed to:
- Instruct the model to run shell commands
- Exfiltrate data via URL construction
- Modify unrelated files
- Introduce backdoors

**Defenses**:
1. Page content is passed in a clearly delineated `<page_content>` block, never mixed with system instructions.
2. The repair agent's system prompt explicitly instructs it to treat page content as data, not instructions.
3. Validation checks (§2.4) catch any forbidden imports, shell commands, or out-of-scope file modifications.
4. The sandbox has no network access and no credentials — even a successful injection has minimal blast radius.
5. Human approval (default mode) provides a final review layer.
