"""
Aegis — Hackathon Visibility Filter

Implements query-time / display-time filtering rules for hackathons:
1. Status Check: Registration is currently open (live) OR start date / event end date is in the future.
   Never show a hackathon whose registration deadline or event end date has already passed.
2. Location/Mode Check: Mode is online/remote OR (mode is in-person/hybrid AND location matches 'Hyderabad' case-insensitively).
   If mode or location is UNKNOWN/missing, it must be excluded by default.
3. Category Specific: Applies strictly to hackathons (jobs & internships pass through).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from core.schemas.domain import OpportunityCategory

ONLINE_MODES = {"remote", "online", "virtual"}
IN_PERSON_MODES = {"onsite", "hybrid", "in_person", "in-person", "offline"}


def _get_attr_or_key(obj: Any, key: str) -> Any:
    """Safely retrieve an attribute or dict key from obj."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _to_datetime(val: Any) -> datetime | None:
    """Parse string or datetime into UTC datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=UTC)
        return val
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str or val_str.lower() in ("none", "null", "unknown"):
            return None
        try:
            dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt
        except Exception:
            return None
    return None


def is_hackathon_status_valid(opp: Any, now: datetime | None = None) -> bool:
    """
    Condition A (Status):
    - Registration is currently open (live) OR its start date is in the future (upcoming).
    - NEVER show a hackathon whose registration deadline or event end date has already passed.
    """
    now_dt = now or datetime.now(UTC)

    reg_deadline = _to_datetime(_get_attr_or_key(opp, "registration_deadline"))
    start_date = _to_datetime(_get_attr_or_key(opp, "start_date"))
    end_date = _to_datetime(_get_attr_or_key(opp, "end_date"))

    # If registration deadline or end date is present and in the past -> EXCLUDE
    if reg_deadline and reg_deadline < now_dt:
        return False
    if end_date and end_date < now_dt:
        return False

    # Check if registration is live or event is in the future
    if reg_deadline and reg_deadline >= now_dt:
        return True
    if end_date and end_date >= now_dt:
        return True
    if start_date and start_date >= now_dt:
        return True

    # If no explicit dates are specified, default to True (open/live unless deadline is passed)
    if reg_deadline is None and end_date is None and start_date is None:
        return True

    return False


def is_hackathon_location_valid(opp: Any) -> bool:
    """
    Condition B (Location/Mode):
    - Mode is online/remote
    - OR (Mode is in-person/hybrid AND location matches 'Hyderabad' case-insensitively).
    - If mode or location is UNKNOWN/missing, exclude by default.
    """
    mode_raw = _get_attr_or_key(opp, "mode")
    loc_raw = _get_attr_or_key(opp, "location")

    if not mode_raw:
        return False

    mode_str = getattr(mode_raw, "value", str(mode_raw)).lower().strip()
    if not mode_str or mode_str in ("unknown", "none", "null"):
        return False

    if mode_str in ONLINE_MODES:
        return True

    if mode_str in IN_PERSON_MODES:
        if not loc_raw:
            return False
        loc_str = str(loc_raw).lower().strip()
        if not loc_str or loc_str in ("unknown", "none", "null"):
            return False
        # Case-insensitive match for Hyderabad (e.g. "Hyderabad", "Hyderabad, Telangana", "Hyderabad, India")
        if re.search(r"\bhyderabad\b", loc_str):
            return True
        return False

    return False


def is_hackathon_visible(opp: Any, now: datetime | None = None) -> bool:
    """
    Main Hackathon Visibility Filter.
    - Applies strictly to hackathons. Jobs & Internships pass through (return True).
    - A hackathon is visible ONLY if BOTH status AND location criteria are satisfied.
    """
    cat_raw = _get_attr_or_key(opp, "category")
    if not cat_raw:
        return True

    cat_str = getattr(cat_raw, "value", str(cat_raw)).lower().strip()
    if cat_str != OpportunityCategory.HACKATHON.value.lower():
        # Non-hackathons are not affected by this filter
        return True

    return is_hackathon_status_valid(opp, now=now) and is_hackathon_location_valid(opp)


def visible_hackathon_filter(opportunities: list[Any], now: datetime | None = None) -> list[Any]:
    """Filter a list of opportunities to return only visible ones."""
    return [opp for opp in opportunities if is_hackathon_visible(opp, now=now)]


def sqlalchemy_visible_hackathon_filter(now: datetime | None = None):
    """
    Generate SQLAlchemy query predicate for database queries.
    Enforces the visibility filter at the ORM level.
    """
    from sqlalchemy import and_, func, not_, or_
    from storage.models.opportunity import Opportunity

    now_dt = now or datetime.now(UTC)

    # Condition A
    status_valid = and_(
        or_(
            Opportunity.registration_deadline.is_(None),
            Opportunity.registration_deadline >= now_dt,
        ),
        or_(
            Opportunity.end_date.is_(None),
            Opportunity.end_date >= now_dt,
        ),
        or_(
            Opportunity.registration_deadline >= now_dt,
            Opportunity.end_date >= now_dt,
            Opportunity.start_date >= now_dt,
            and_(
                Opportunity.registration_deadline.is_(None),
                Opportunity.end_date.is_(None),
                Opportunity.start_date.is_(None),
            ),
        ),
    )

    # Condition B
    location_valid = or_(
        func.lower(Opportunity.mode).in_(["remote", "online", "virtual"]),
        and_(
            func.lower(Opportunity.mode).in_(["onsite", "hybrid", "in_person", "in-person", "offline"]),
            Opportunity.location.is_not(None),
            not_(func.lower(Opportunity.location).in_(["unknown", "none", "", "null"])),
            func.lower(Opportunity.location).like("%hyderabad%"),
        ),
    )

    return or_(
        func.lower(Opportunity.category) != OpportunityCategory.HACKATHON.value.lower(),
        and_(status_valid, location_valid),
    )
