"""
Unit tests for FastAPI health endpoints (/health/live and /health/ready).

Verifies that:
1. /health/live always returns 200 OK.
2. /health/ready returns 200 OK when both DB and Redis probes pass.
3. /health/ready returns 503 Service Unavailable when DB is down.
4. /health/ready returns 503 Service Unavailable when Redis is down.
"""

from unittest.mock import AsyncMock, patch

import pytest
from apps.api.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_live_endpoint():
    """Verify liveness probe returns HTTP 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data
        assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_health_ready_all_healthy():
    """Verify readiness probe returns HTTP 200 when DB and Redis are healthy."""
    transport = ASGITransport(app=app)
    with (
        patch("apps.api.main.check_db_connectivity", new_callable=AsyncMock) as mock_db,
        patch("apps.api.main.check_redis_connectivity", new_callable=AsyncMock) as mock_redis,
    ):
        mock_db.return_value = (True, "ok")
        mock_redis.return_value = (True, "ok")

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["components"]["database"]["status"] == "ok"
            assert data["components"]["redis"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_ready_db_down():
    """Verify readiness probe returns HTTP 503 when Database is unreachable."""
    transport = ASGITransport(app=app)
    with (
        patch("apps.api.main.check_db_connectivity", new_callable=AsyncMock) as mock_db,
        patch("apps.api.main.check_redis_connectivity", new_callable=AsyncMock) as mock_redis,
    ):
        mock_db.return_value = (False, "Connection refused")
        mock_redis.return_value = (True, "ok")

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["components"]["database"]["status"] == "down"
            assert data["components"]["redis"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_ready_redis_down():
    """Verify readiness probe returns HTTP 503 when Redis is unreachable."""
    transport = ASGITransport(app=app)
    with (
        patch("apps.api.main.check_db_connectivity", new_callable=AsyncMock) as mock_db,
        patch("apps.api.main.check_redis_connectivity", new_callable=AsyncMock) as mock_redis,
    ):
        mock_db.return_value = (True, "ok")
        mock_redis.return_value = (False, "Redis connection timeout")

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["components"]["database"]["status"] == "ok"
            assert data["components"]["redis"]["status"] == "down"


@pytest.mark.asyncio
async def test_root_endpoint():
    """Verify root API discovery endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "operational"
        assert "version" in data
