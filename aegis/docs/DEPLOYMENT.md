# Aegis — Production Deployment & Security Hardening Guide

This document details the production containerization, environment configuration, health monitoring, and security posture of the **AEGIS Autonomous Opportunity Intelligence Platform**.

---

## 1. Stack Architecture & Containers

Aegis is fully containerized using multi-stage Docker builds and orchestrated via `docker-compose.yml`:

| Service | Container Name | Image / Base | External Port | Function |
|---|---|---|---|---|
| **PostgreSQL** | `aegis-postgres` | `pgvector/pgvector:pg16` | `5432` | Relational DB + pgvector extension for embeddings |
| **Redis** | `aegis-redis` | `redis:7-alpine` | `6379` | Celery message broker & rate limit store |
| **API Backend** | `aegis-api` | `Dockerfile.api` | `8000` | FastAPI REST API engine |
| **Worker** | `aegis-worker` | `Dockerfile.worker` | - | Celery autonomous extraction & repair tasks |
| **Beat** | `aegis-beat` | `Dockerfile.worker` | - | Celery Beat periodic scheduler |
| **Dashboard** | `aegis-dashboard` | `Dockerfile.dashboard` | `5173` | React frontend served via Nginx |

---

## 2. Environment Variables & Secrets Management

All configuration is externalized via `pydantic-settings` (`core/config/settings.py`). Production deployment settings must be supplied via `.env` or container environment overrides:

```ini
# Database & Broker
DATABASE_URL=postgresql+asyncpg://aegis:aegis_password@postgres:5432/aegis_db
REDIS_URL=redis://redis:6379/0

# Environment & Logging
ENVIRONMENT=production
LOG_LEVEL=INFO
CORS_ORIGINS=["http://localhost:5173"]

# API Security Key
API_SECRET_KEY=your-secure-production-api-key-here

# Self-Healing Pipeline Toggles
AEGIS_REPAIR_ENABLED=true
AEGIS_AUTO_PROMOTE_REPAIRS=false
```

---

## 3. Launching with Docker Compose

1. **Build and Start all Services**:
   ```bash
   docker-compose up -d --build
   ```

2. **Apply Database Migrations**:
   ```bash
   docker-compose exec api alembic upgrade head
   ```

3. **Verify Service Health**:
   ```bash
   curl http://localhost:8000/health/ready
   ```
   Expected response:
   ```json
   {
     "status": "ready",
     "timestamp": "2026-09-12T12:00:00Z",
     "components": {
       "database": {"status": "ok", "message": "PostgreSQL connection successful"},
       "redis": {"status": "ok", "message": "Redis connection successful"}
     }
   }
   ```

4. **Access UI Dashboard**:
   Open browser at `http://localhost:5173`.

---

## 4. Security Hardening Posture

1. **SSRF Hardening**:
   Outbound HTTP requests via `RestrictedHttpClient` resolve destination IPs and enforce strict rejection of:
   - Loopback (`127.0.0.1`, `::1`)
   - Private RFC 1918 networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
   - Link-local and cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`, `instance-data`)
   - Hostnames outside configured per-source domain allowlists.

2. **API Authentication**:
   Sensitive administrative endpoints require valid `X-API-Key` headers using timing-safe comparison (`hmac.compare_digest`).

3. **AST Security Validation Gate**:
   Self-healing code patches undergo static analysis before execution. Blocked operations include:
   - `subprocess`, `os.system`, `eval`, `exec`, `__import__`
   - File creation outside `connectors/` directory
   - Diff patches > 200 lines
   - Hardcoded secret patterns (API keys, private keys, AWS credentials)

4. **Adversarial Prompt Injection Defense**:
   Untrusted HTML snapshots and résumés are sanitized prior to prompt construction:
   - Script, style, and HTML comment tags stripped
   - Hostile instructions redacted with `[REDACTED_INJECTED_INSTRUCTION]`
   - Snapshot token size capped to prevent context flooding.
