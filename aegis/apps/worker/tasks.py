"""
Aegis — Celery Tasks & Autonomous Collection Engine

Implements scheduled background ingestion jobs with content hash deduplication,
run metrics logging, retry/exponential backoff, and health state machine transitions.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from apps.worker.celery_app import celery_app
from connectors.base import BaseConnector, TransientConnectorError
from connectors.registry import get_connector
from core.logging.logger import setup_logging
from sqlalchemy.ext.asyncio import AsyncSession
from storage.database import AsyncSessionLocal
from storage.repositories.opportunity_repository import OpportunityRepository
from storage.repositories.snapshot_repository import SnapshotRepository
from storage.repositories.source_repository import SourceRepository

logger = setup_logging()


async def execute_source_collection(
    session: AsyncSession,
    source_id: uuid.UUID,
    force: bool = False,
    connector_override: BaseConnector | None = None,
) -> dict[str, Any]:
    """
    Core async logic for collecting from a source:
    1. Look up source in DB.
    2. Check enabled state.
    3. Run connector.fetch().
    4. Check for duplicate snapshot hash (idempotency).
    5. If new: persist snapshot, normalize records, upsert opportunities.
    6. Record run metric and update health transition state.
    """
    start_time = time.perf_counter()
    source = await SourceRepository.get_by_id(session, source_id)
    if not source:
        return {"status": "failed", "error": f"Source {source_id} not found"}

    if not source.enabled and not force:
        return {"status": "skipped", "reason": "Source is disabled"}

    try:
        connector = connector_override or get_connector(source.connector_class)
    except Exception as exc:
        duration = time.perf_counter() - start_time
        await SourceRepository.record_run_outcome(session, source_id, success=False)
        await SnapshotRepository.record_source_run(
            session,
            source_id=source_id,
            status="failure",
            record_count=0,
            duration_seconds=duration,
            error_message=f"Connector lookup error: {exc}",
        )
        await session.commit()
        raise

    try:
        fetch_result = await connector.fetch(source.connector_config)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
        duration = time.perf_counter() - start_time
        await SourceRepository.record_run_outcome(session, source_id, success=False)
        await SnapshotRepository.record_source_run(
            session,
            source_id=source_id,
            status="failure",
            record_count=0,
            duration_seconds=duration,
            error_message=str(exc),
        )
        await session.commit()
        raise TransientConnectorError(f"Transient network failure fetching {source.name}: {exc}") from exc
    except Exception as exc:
        duration = time.perf_counter() - start_time
        await SourceRepository.record_run_outcome(session, source_id, success=False)
        await SnapshotRepository.record_source_run(
            session,
            source_id=source_id,
            status="failure",
            record_count=0,
            duration_seconds=duration,
            error_message=str(exc),
        )
        await session.commit()
        raise

    # Check for duplicate raw snapshot hash (idempotency check)
    existing_snapshot = await SnapshotRepository.get_snapshot_by_hash(
        session,
        source_id,
        fetch_result.content_hash,
    )

    duration = time.perf_counter() - start_time

    if existing_snapshot and not force:
        # Content has not changed since last crawl; record run but skip duplicating snapshot/opportunities
        await SnapshotRepository.record_source_run(
            session,
            source_id=source_id,
            status="unchanged",
            record_count=0,
            duration_seconds=duration,
        )
        await SourceRepository.record_run_outcome(session, source_id, success=True)
        await session.commit()
        return {
            "status": "unchanged",
            "source_id": str(source_id),
            "content_hash": fetch_result.content_hash,
            "records_collected": 0,
            "duration_seconds": round(duration, 3),
        }

    # Save new raw snapshot
    await SnapshotRepository.save_raw_snapshot(
        session,
        source_id=source_id,
        content_hash=fetch_result.content_hash,
        raw_payload=fetch_result.raw_payload,
        record_count=len(fetch_result.records),
        collected_at=fetch_result.fetch_timestamp,
    )

    # Normalize records into canonical OpportunitySchema and upsert
    normalized_count = 0
    for raw_item in fetch_result.records:
        try:
            opp_schema = connector.normalize_raw(raw_item, source.id)
            await OpportunityRepository.upsert_opportunity(session, opp_schema)
            normalized_count += 1
        except Exception as norm_err:
            logger.warning(f"Failed to normalize item from source {source.id}: {norm_err}")

    # Record successful run metrics and transition source health
    await SnapshotRepository.record_source_run(
        session,
        source_id=source_id,
        status="success",
        record_count=normalized_count,
        duration_seconds=duration,
    )
    await SourceRepository.record_run_outcome(session, source_id, success=True)
    await session.commit()

    return {
        "status": "success",
        "source_id": str(source_id),
        "content_hash": fetch_result.content_hash,
        "records_collected": normalized_count,
        "duration_seconds": round(duration, 3),
    }


# ---------------------------------------------------------------------------
# Celery Tasks
# ---------------------------------------------------------------------------


@celery_app.task(name="aegis.proof_of_life")
def proof_of_life_task(echo: str = "pong") -> dict[str, Any]:
    """Trivial proof-of-life task to verify worker task dispatch and execution."""
    logger.info(f"Executing proof-of-life task with echo={echo}")
    return {
        "status": "success",
        "echo": echo,
        "worker_timestamp": datetime.now(UTC).isoformat(),
    }


@celery_app.task(
    bind=True,
    name="aegis.collect_source",
    max_retries=3,
    default_retry_delay=5,
    autoretry_for=(TransientConnectorError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def collect_source_task(self, source_id_str: str, force: bool = False) -> dict[str, Any]:
    """
    Celery task to run autonomous collection for a single source.
    Automatically retries transient network errors with exponential backoff.
    """
    source_id = uuid.UUID(source_id_str)

    async def _runner() -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            return await execute_source_collection(session, source_id, force=force)

    return asyncio.run(_runner())


@celery_app.task(name="aegis.sweep_and_dispatch_sources")
def sweep_and_dispatch_sources_task() -> dict[str, Any]:
    """
    Periodic Celery Beat task that inspects all enabled sources and queues
    collection tasks for sources due for ingestion.
    """
    async def _sweep() -> list[str]:
        dispatched = []
        async with AsyncSessionLocal() as session:
            sources = await SourceRepository.list_sources(session, enabled_only=True)
            for source in sources:
                # Dispatch collection task asynchronously
                collect_source_task.delay(str(source.id))
                dispatched.append(str(source.id))
        return dispatched

    dispatched_ids = asyncio.run(_sweep())
    return {
        "status": "dispatched",
        "count": len(dispatched_ids),
        "source_ids": dispatched_ids,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@celery_app.task(name="aegis.evaluate_and_rank_opportunity")
def evaluate_and_rank_opportunity_task(opportunity_id_str: str) -> dict[str, Any]:
    """
    Celery task that scores an opportunity against all active confirmed student profiles,
    persisting EligibilityDecision and MatchScore records.
    """
    opp_id = uuid.UUID(opportunity_id_str)

    async def _evaluate() -> dict[str, Any]:
        from core.schemas.domain import OpportunitySchema, ProfileSchema
        from opportunity.ranking.engine import RankingEngine
        from storage.repositories.eligibility_repository import EligibilityRepository
        from storage.repositories.match_repository import MatchRepository
        from storage.repositories.profile_repository import ProfileRepository

        async with AsyncSessionLocal() as session:
            opp = await OpportunityRepository.get_by_id(session, opp_id)
            if not opp:
                return {"status": "skipped", "reason": "Opportunity not found"}

            confirmed_profiles = await ProfileRepository.list_all_confirmed(session)
            if not confirmed_profiles:
                return {"status": "skipped", "reason": "No confirmed profiles to match against"}

            engine = RankingEngine()
            opp_schema = OpportunitySchema.model_validate(opp)
            elig_repo = EligibilityRepository(session)
            match_repo = MatchRepository(session)

            evaluated = 0
            for prof in confirmed_profiles:
                p_schema = ProfileSchema.model_validate(prof)
                match_score, elig_decision = engine.score_pair(p_schema, opp_schema)

                await elig_repo.save_decision(
                    opportunity_id=opp.id,
                    profile_id=prof.id,
                    state=elig_decision.state,
                    evidence=elig_decision.evidence,
                    rule_results=elig_decision.rule_results,
                    confidence=elig_decision.confidence,
                )
                await match_repo.save_match_score(
                    opportunity_id=opp.id,
                    profile_id=prof.id,
                    final_score=match_score.final_score,
                    eligibility_score=match_score.eligibility_score,
                    feature_overlap_score=match_score.feature_overlap_score,
                    semantic_similarity_score=match_score.semantic_similarity_score,
                    weights_used=match_score.weights_used,
                    score_breakdown=match_score.score_breakdown,
                    explanation=match_score.explanation,
                )
                evaluated += 1

            await session.commit()

            # Trigger notification dispatch asynchronously
            dispatch_opportunity_notifications_task.delay(str(opp_id))

            return {
                "status": "success",
                "opportunity_id": str(opp_id),
                "profiles_evaluated": evaluated,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    return asyncio.run(_evaluate())


@celery_app.task(name="aegis.dispatch_opportunity_notifications")
def dispatch_opportunity_notifications_task(opportunity_id_str: str) -> dict[str, Any]:
    """
    Dispatches immediate match notifications to confirmed profiles who scored high on an opportunity.
    """
    opp_id = uuid.UUID(opportunity_id_str)

    async def _dispatch() -> dict[str, Any]:
        from notifications.dispatcher import NotificationDispatcher
        from storage.repositories.eligibility_repository import EligibilityRepository
        from storage.repositories.match_repository import MatchRepository
        from storage.repositories.profile_repository import ProfileRepository

        async with AsyncSessionLocal() as session:
            opp = await OpportunityRepository.get_by_id(session, opp_id)
            if not opp:
                return {"status": "skipped", "reason": "Opportunity not found"}

            confirmed_profiles = await ProfileRepository.list_all_confirmed(session)
            if not confirmed_profiles:
                return {"status": "skipped", "reason": "No confirmed profiles"}

            dispatcher = NotificationDispatcher(session)
            match_repo = MatchRepository(session)
            elig_repo = EligibilityRepository(session)

            dispatched_count = 0
            for prof in confirmed_profiles:
                match_score = await match_repo.get_by_pair(opp.id, prof.id)
                eligibility = await elig_repo.get_by_pair(opp.id, prof.id)
                if match_score and eligibility:
                    notif = await dispatcher.dispatch_immediate_match(
                        profile=prof,
                        opportunity=opp,
                        match_score=match_score,
                        eligibility=eligibility,
                    )
                    if notif:
                        dispatched_count += 1

            await session.commit()
            return {
                "status": "success",
                "opportunity_id": str(opp_id),
                "notifications_created": dispatched_count,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    return asyncio.run(_dispatch())


@celery_app.task(name="aegis.send_daily_digests")
def send_daily_digests_task() -> dict[str, Any]:
    """
    Periodic Celery Beat task to compile and deliver consolidated daily opportunity digests.
    """
    async def _digest() -> dict[str, Any]:
        from notifications.dispatcher import NotificationDispatcher
        from storage.repositories.match_repository import MatchRepository
        from storage.repositories.profile_repository import ProfileRepository

        async with AsyncSessionLocal() as session:
            confirmed_profiles = await ProfileRepository.list_all_confirmed(session)
            dispatcher = NotificationDispatcher(session)
            match_repo = MatchRepository(session)
            digests_sent = 0

            for prof in confirmed_profiles:
                ranked = await match_repo.get_ranked_matches(prof.id, min_score=0.60, limit=10)
                if not ranked:
                    continue

                items = []
                for m in ranked:
                    opp = await OpportunityRepository.get_by_id(session, m.opportunity_id)
                    if not opp:
                        continue
                    deadline_str = (
                        opp.registration_deadline.strftime("%B %d, %Y")
                        if opp.registration_deadline
                        else "Rolling"
                    )
                    items.append({
                        "opportunity_id": str(opp.id),
                        "title": opp.title,
                        "category": opp.category or "opportunity",
                        "match_score": m.final_score,
                        "eligibility_state": (
                            m.score_breakdown.get("eligibility", {}).get("state", "UNKNOWN")
                            if m.score_breakdown
                            else "UNKNOWN"
                        ),
                        "deadline": deadline_str,
                        "explanation": m.explanation,
                        "source_url": opp.url,
                    })

                if items:
                    notif = await dispatcher.dispatch_daily_digest(profile=prof, top_items=items)
                    if notif:
                        digests_sent += 1

            await session.commit()
            return {
                "status": "success",
                "digests_sent": digests_sent,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    return asyncio.run(_digest())


@celery_app.task(name="aegis.process_pending_notifications")
def process_pending_notifications_task() -> dict[str, Any]:
    """
    Periodic Celery Beat task that sweeps and delivers deferred notifications whose quiet hours have passed.
    """
    async def _process() -> dict[str, Any]:
        from notifications.dispatcher import NotificationDispatcher

        async with AsyncSessionLocal() as session:
            dispatcher = NotificationDispatcher(session)
            delivered = await dispatcher.process_pending_scheduled()
            await session.commit()
            return {
                "status": "success",
                "delivered_count": delivered,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    return asyncio.run(_process())


@celery_app.task(name="aegis.run_connector_repair")
def run_connector_repair_task(
    source_id_str: str,
    target_file_rel: str,
    failure_class_str: str = "selector_not_found",
    error_summary: str | None = None,
    raw_snapshot: str | None = None,
    broken_selector: str | None = None,
    fixed_selector: str | None = None,
) -> dict[str, Any]:
    """
    Celery task to run the autonomous self-healing pipeline for a broken connector.
    """
    source_id = uuid.UUID(source_id_str)

    async def _repair() -> dict[str, Any]:
        from agents.orchestrator.repair_orchestrator import RepairOrchestrator

        async with AsyncSessionLocal() as session:
            orchestrator = RepairOrchestrator(session)
            run, patch = await orchestrator.execute_self_healing_run(
                source_id=source_id,
                target_file_rel=target_file_rel,
                failure_class=failure_class_str,
                error_summary=error_summary,
                raw_snapshot=raw_snapshot,
                broken_selector=broken_selector,
                fixed_selector=fixed_selector,
            )
            await session.commit()
            return {
                "status": "success",
                "repair_run_id": str(run.id),
                "patch_id": str(patch.id) if patch else None,
                "patch_state": patch.state if patch else None,
                "outcome": run.outcome,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    return asyncio.run(_repair())


