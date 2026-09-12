# AEGIS — Autonomous Opportunity Intelligence Platform

[![Build Status](https://img.shields.io/badge/Build-Phase%2010%20Completed-brightgreen.svg)](docs/BUILD_STATUS.md)
[![Test Suite](https://img.shields.io/badge/Tests-245%2F245%20Passing-success.svg)](#testing--evaluation)
[![Python Version](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](Dockerfile.api)
[![React Dashboard](https://img.shields.io/badge/Dashboard-Vite%20%2B%20TypeScript-blueviolet.svg)](apps/dashboard/)

**AEGIS** is an autonomous opportunity intelligence platform designed to discover, extract, normalize, match, rank, and alert candidates on high-value career opportunities (hackathons, internships, fellowships, and software roles) while automatically diagnosing and self-healing broken web connectors without human intervention.

---

## 🌟 Key Features

- **Profile & Résumé Intelligence**: Deterministic PDF/text extraction combined with LLM structuring, prompt injection defense, and skill taxonomy normalization.
- **Multi-Source Autonomous Ingestion**: Greenhouse API, Lever API, RSS/Atom feeds, and multi-strategy HTML web scraper with token-bucket rate limiting and SSRF protection.
- **Hybrid Matching & Ranking Engine**: Transparent scoring combining hard eligibility constraints (Hard Exclusion Dominance), structured feature overlap, and semantic embeddings with fact-grounded explanations.
- **Deduplicated Notification Center**: Multi-channel alerting (In-App, Email, Telegram) with quiet hours scheduling and SHA-256 idempotency key deduplication.
- **Self-Healing Connector Pipeline**: Automated failure classification, LLM unified diff synthesis, AST security validation gate, sandboxed verification, and human-in-the-loop approval.
- **Observability & Benchmark Suite**: Quantitative evaluation runner computing Precision/Recall, Eligibility Accuracy, Ranking P@5/P@10, OpenTelemetry tracing, and an 8-mode chaos resilience suite.
- **Production Containerization & Hardening**: Multi-stage Docker images (`Dockerfile.api`, `Dockerfile.worker`, `Dockerfile.dashboard`) and `docker-compose.yml` with PostgreSQL (pgvector) and Redis.

---

## 📊 Phased Build Matrix

| Phase | Phase Name | Status | Test Verification |
|---|---|---|---|
| **Phase 0** | **Specification, Rules & Repository Contract** | **COMPLETED** | All schema, architecture, & security contracts locked. |
| **Phase 1** | **Production Scaffold & Local Infrastructure** | **COMPLETED** | FastAPI, Celery, React+TS, Alembic pgvector, Docker. |
| **Phase 2** | **Profile & Résumé Intelligence** | **COMPLETED** | 47/47 unit tests passing. |
| **Phase 3** | **Source Registry, API Connectors & Scheduling** | **COMPLETED** | 76/76 unit tests passing. |
| **Phase 4** | **Web Extraction & Hackathon Intelligence** | **COMPLETED** | 112/112 unit tests passing. |
| **Phase 5** | **Eligibility, Matching, Ranking & Explainability** | **COMPLETED** | 197/197 unit tests passing. |
| **Phase 6** | **Notifications, Scheduler & User Experience** | **COMPLETED** | 222/222 unit tests passing. |
| **Phase 7** | **Self-Healing Connector System** | **COMPLETED** | 232/232 unit tests passing. |
| **Phase 8** | **Observability, Evaluation & Reliability** | **COMPLETED** | 240/240 unit tests passing (incl. 8 chaos modes). |
| **Phase 9** | **Security, Deployment & Production Hardening** | **COMPLETED** | 245/245 unit tests passing (SSRF, auth, containerization). |
| **Phase 10** | **Documentation, Demo & Delivery Readiness** | **COMPLETED** | Seed scripts, self-healing demo, README & full sign-off. |

---

## 🚀 Local Quickstart

### Prerequisites
- **Python**: `3.11+`
- **Node.js**: `v20+`
- **Docker**: `24+` & `Docker Compose 2.20+` (optional for full-stack dockerization)

### Option A: Running via Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/aegis-intelligence/aegis.git
cd aegis

# 2. Start all services (Postgres, Redis, API, Worker, Beat, Dashboard)
docker-compose up -d --build

# 3. Apply database migrations
docker-compose exec api alembic upgrade head

# 4. Access UI Dashboard
# Open http://localhost:5173 in your browser
```

### Option B: Standalone Python & Vite Setup

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Run test suite to verify installation
python -m pytest

# 3. Run FastAPI backend
uvicorn apps.api.main:app --reload --port 8000

# 4. Run React Dashboard (in a separate terminal)
cd apps/dashboard
npm install
npm run dev
```

---

## 🛠️ Interactive Demonstrations

### 1. Seed Sample Database Records
Generates sample sources, candidate profiles, hackathon opportunities, hybrid match scores, and notifications:
```bash
python scripts/seed_demo.py
```

### 2. Run Self-Healing Connector Demonstration
Simulates a broken DOM selector failure, classifies the anomaly, synthesizes a minimal unified diff patch, enforces AST security checks, and restores source health:
```bash
python scripts/demo_self_healing.py
```

---

## 🧪 Testing & Evaluation

Run the full automated test suite (245/245 tests):
```bash
# Full test suite
python -m pytest -v

# Chaos resilience test suite (8 operational failure modes)
python -m pytest tests/chaos/ -v

# Security hardening test suite
python -m pytest tests/security/ -v
```

---

## 📚 Documentation Index

Detailed architectural and technical guides located in [`docs/`](docs/):
- **[`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)**: Database schemas, domain models & ER diagram.
- **[`docs/EVALUATION.md`](docs/EVALUATION.md)**: Benchmark runner, quantitative metrics & chaos test methodology.
- **[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)**: Production deployment, Docker Compose, secrets management & SSRF posture.
- **[`docs/BUILD_STATUS.md`](docs/BUILD_STATUS.md)**: Full 11-phase progress tracker & verification sign-offs.
