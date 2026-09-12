"""
Aegis — Notification Idempotency & Version Hashing (AC-4.2, AC-4.3)

Implements stable SHA-256 idempotency keys:
    SHA256(user_id + opportunity_id + version_hash)

Re-notification occurs strictly when meaningful fields change (deadline, title, mode,
compensation, requirements), never on no-op re-crawls or metadata refreshes.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from core.schemas.domain import OpportunitySchema


def compute_opportunity_version_hash(
    opportunity: OpportunitySchema | dict[str, Any],
) -> str:
    """
    Computes a deterministic hash of meaningful opportunity fields.
    Excludes volatile metadata (timestamps, snapshot IDs, DB keys).
    A change in this hash triggers re-notification eligibility.
    """
    if isinstance(opportunity, OpportunitySchema):
        data = opportunity.model_dump()
    elif hasattr(opportunity, "__dict__"):
        dl = getattr(opportunity, "registration_deadline", None)
        dl_str = dl.isoformat() if (dl is not None and hasattr(dl, "isoformat")) else (str(dl) if dl else None)
        data = {
            "title": getattr(opportunity, "title", ""),
            "category": getattr(opportunity, "category", ""),
            "mode": getattr(opportunity, "mode", ""),
            "location": getattr(opportunity, "location", None),
            "registration_deadline": dl_str,
            "salary_range": getattr(opportunity, "salary_range", None),
            "requirements": getattr(opportunity, "requirements", []),
            "description": getattr(opportunity, "description", ""),
        }
    else:
        data = dict(opportunity)

    # Pick only meaningful fields
    deadline = data.get("registration_deadline")
    if deadline is not None and hasattr(deadline, "isoformat"):
        deadline_str = deadline.isoformat()
    elif deadline is not None:
        deadline_str = str(deadline)
    else:
        deadline_str = None

    requirements = data.get("requirements") or []
    if isinstance(requirements, list):
        sorted_reqs = sorted(str(r) for r in requirements)
    else:
        sorted_reqs = [str(requirements)]

    meaningful_payload = {
        "title": str(data.get("title", "")).strip().lower(),
        "category": str(data.get("category", "")).strip().lower(),
        "mode": str(data.get("mode", "")).strip().lower(),
        "location": str(data.get("location") or "").strip().lower(),
        "deadline": deadline_str,
        "salary_range": str(data.get("salary_range") or "").strip().lower(),
        "requirements": sorted_reqs,
    }

    serialized = json.dumps(meaningful_payload, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def compute_idempotency_key(
    user_id: uuid.UUID | str,
    opportunity_id: uuid.UUID | str,
    version_hash: str,
) -> str:
    """
    Computes the stable notification idempotency key per Build Directive §2.7:
        SHA256(user_id + opportunity_id + version_hash)
    """
    raw_str = f"{user_id}:{opportunity_id}:{version_hash}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


def compute_digest_idempotency_key(
    user_id: uuid.UUID | str,
    digest_date: str,
) -> str:
    """
    Computes the idempotency key for a daily digest:
        SHA256(user_id + "digest" + YYYY-MM-DD)
    Prevents duplicate digests on the same day.
    """
    raw_str = f"{user_id}:digest:{digest_date}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
