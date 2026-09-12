"""
Aegis — FastAPI Application Skeleton

Provides health check probes (/health/live, /health/ready), correlation ID tracking,
and core middleware for the Aegis backend API.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from apps.api.routers.feed import router as feed_router
from apps.api.routers.metrics import metrics_router
from apps.api.routers.notifications import router as notifications_router
from apps.api.routers.profile import router as profile_router
from apps.api.routers.repair import router as repair_router
from apps.api.routers.source import router as source_router
from core.config.settings import get_settings
from core.logging.logger import set_correlation_id, setup_logging
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from storage.database import check_db_connectivity, check_redis_connectivity

settings = get_settings()
logger = setup_logging(settings.log_level)


def create_app() -> FastAPI:
    """Application factory for the Aegis FastAPI backend."""
    app = FastAPI(
        title="Aegis API",
        description="Autonomous Student Opportunity Intelligence Platform API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Register Routers
    app.include_router(profile_router)
    app.include_router(source_router)
    app.include_router(feed_router)
    app.include_router(notifications_router)
    app.include_router(repair_router)
    app.include_router(metrics_router)


    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Correlation ID & Timing Middleware
    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next) -> Response:
        # Extract existing X-Request-ID or generate new UUID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        set_correlation_id(request_id)

        start_time = time.perf_counter()
        try:
            response: Response = await call_next(request)
            process_time = (time.perf_counter() - start_time) * 1000
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
            return response
        except Exception as exc:
            process_time = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"Unhandled exception processing {request.method} {request.url.path}: {exc}",
                exc_info=True,
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal Server Error",
                    "request_id": request_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                headers={
                    "X-Request-ID": request_id,
                    "X-Process-Time-Ms": f"{process_time:.2f}",
                },
            )

    # ---------------------------------------------------------------------------
    # Health Endpoints
    # ---------------------------------------------------------------------------

    @app.get("/health/live", tags=["Health"], summary="Liveness probe")
    async def health_live() -> dict[str, Any]:
        """
        Lightweight liveness probe.
        Returns 200 OK if the FastAPI process is responsive.
        """
        return {
            "status": "alive",
            "environment": settings.environment,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @app.get("/health/ready", tags=["Health"], summary="Readiness probe")
    async def health_ready() -> Response:
        """
        Readiness probe.
        Checks connectivity to both PostgreSQL and Redis.
        Returns 200 OK if both are reachable, 503 Service Unavailable otherwise.
        """
        db_ok, db_msg = await check_db_connectivity()
        redis_ok, redis_msg = await check_redis_connectivity()

        is_ready = db_ok and redis_ok
        status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

        payload = {
            "status": "ready" if is_ready else "not_ready",
            "timestamp": datetime.now(UTC).isoformat(),
            "components": {
                "database": {"status": "ok" if db_ok else "down", "message": db_msg},
                "redis": {"status": "ok" if redis_ok else "down", "message": redis_msg},
            },
        }

        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/", tags=["Root"])
    async def root() -> dict[str, Any]:
        return {
            "name": "Aegis Opportunity Intelligence API",
            "version": "0.1.0",
            "docs": "/docs",
            "status": "operational",
        }

    return app


app = create_app()
