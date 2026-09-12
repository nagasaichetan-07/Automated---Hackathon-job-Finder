"""
Aegis — Source Registry API Router

Endpoints for managing data sources, monitoring source health states,
triggering test runs, and viewing collection audit metrics.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from connectors.registry import get_connector
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from storage.database import get_db_session
from storage.repositories.snapshot_repository import SnapshotRepository
from storage.repositories.source_repository import SourceRepository

router = APIRouter(prefix="/api/v1/sources", tags=["Sources"])


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------


class SourceCreateRequest(BaseModel):
    """Payload to register a new data source."""

    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., pattern=r"^(api|web|rss)$")
    url: str = Field(..., min_length=1)
    connector_class: str = Field(..., min_length=1)
    connector_config: dict[str, Any] = Field(default_factory=dict)
    cadence: str = Field(default="0 */6 * * *")
    enabled: bool = True
    access_notes: str | None = None


class SourceUpdateRequest(BaseModel):
    """Payload to modify an existing data source."""

    name: str | None = None
    url: str | None = None
    source_type: str | None = None
    connector_class: str | None = None
    connector_config: dict[str, Any] | None = None
    cadence: str | None = None
    enabled: bool | None = None
    access_notes: str | None = None


class SourceResponse(BaseModel):
    """Public representation of a registered data source."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    source_type: str
    url: str
    connector_class: str
    connector_config: dict[str, Any]
    cadence: str
    enabled: bool
    health_state: str
    access_notes: str | None
    consecutive_failures: int
    last_run_at: datetime | None
    last_success_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SourceDetailResponse(SourceResponse):
    """Detailed view including recent execution runs."""

    recent_runs: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[SourceResponse], summary="List data sources")
async def list_sources(
    enabled_only: bool = Query(False, description="Filter only enabled sources"),
    health_state: str | None = Query(None, description="Filter by health state (healthy/degraded/broken)"),
    session: AsyncSession = Depends(get_db_session),
) -> list[SourceResponse]:
    """Retrieve all configured data sources with optional health filtering."""
    sources = await SourceRepository.list_sources(
        session,
        enabled_only=enabled_only,
        health_state=health_state,
    )
    return [SourceResponse.model_validate(s) for s in sources]


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED, summary="Create data source")
async def create_source(
    payload: SourceCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> SourceResponse:
    """Register a new data source."""
    source = await SourceRepository.create_source(
        session,
        name=payload.name,
        source_type=payload.source_type,
        url=payload.url,
        connector_class=payload.connector_class,
        connector_config=payload.connector_config,
        cadence=payload.cadence,
        enabled=payload.enabled,
        access_notes=payload.access_notes,
    )
    await session.commit()
    await session.refresh(source)
    return SourceResponse.model_validate(source)


@router.get("/{source_id}", response_model=SourceDetailResponse, summary="Get source details and run audit")
async def get_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> SourceDetailResponse:
    """Retrieve detailed source information including recent run execution history."""
    source = await SourceRepository.get_by_id(session, source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source with id '{source_id}' not found",
        )

    runs = await SnapshotRepository.list_runs_for_source(session, source_id, limit=10)
    run_dicts = [
        {
            "id": str(r.id),
            "status": r.status,
            "record_count": r.record_count,
            "duration_seconds": r.duration_seconds,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat(),
        }
        for r in runs
    ]

    resp_data = SourceResponse.model_validate(source).model_dump()
    return SourceDetailResponse(**resp_data, recent_runs=run_dicts)


@router.patch("/{source_id}", response_model=SourceResponse, summary="Update data source")
async def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> SourceResponse:
    """Update configuration or enable/disable a data source."""
    updated = await SourceRepository.update_source(
        session,
        source_id,
        **payload.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source with id '{source_id}' not found",
        )
    await session.commit()
    await session.refresh(updated)
    return SourceResponse.model_validate(updated)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete data source")
async def delete_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a data source."""
    deleted = await SourceRepository.delete_source(session, source_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source with id '{source_id}' not found",
        )
    await session.commit()


@router.post("/{source_id}/test", summary="Test connector connection and health")
async def test_source_connection(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Execute an immediate health probe against the source."""
    source = await SourceRepository.get_by_id(session, source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source with id '{source_id}' not found",
        )

    try:
        connector = get_connector(source.connector_class)
        result = await connector.health_check(source.connector_config)
        return {
            "source_id": str(source.id),
            "healthy": result.healthy,
            "status_code": result.status_code,
            "latency_ms": result.latency_ms,
            "message": result.message,
        }
    except Exception as exc:
        return {
            "source_id": str(source.id),
            "healthy": False,
            "latency_ms": 0.0,
            "message": f"Health check failed: {exc}",
        }
