"""
Aegis — Quiet Hours Enforcement (AC-4.4)

Ensures notifications respect user resting periods (default 22:00 to 08:00).
During quiet hours, immediate notifications are scheduled for delivery when quiet hours end.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def is_in_quiet_hours(
    current_time: datetime | None = None,
    quiet_start: int = 22,
    quiet_end: int = 8,
) -> bool:
    """
    Checks if a given timestamp falls within quiet hours.
    Default: 22:00 (10 PM) to 08:00 (8 AM) next day.
    """
    t = current_time or datetime.now(UTC)
    hour = t.hour

    if quiet_start > quiet_end:
        # Spans midnight (e.g. 22:00 to 08:00)
        return hour >= quiet_start or hour < quiet_end
    if quiet_start < quiet_end:
        # Within the same day (e.g. 13:00 to 15:00)
        return quiet_start <= hour < quiet_end
    # quiet_start == quiet_end means quiet hours are disabled
    return False


def next_active_time(
    current_time: datetime | None = None,
    quiet_start: int = 22,
    quiet_end: int = 8,
) -> datetime:
    """
    Calculates the next active timestamp when quiet hours end.
    If not currently in quiet hours, returns current_time.
    """
    t = current_time or datetime.now(UTC)

    if not is_in_quiet_hours(t, quiet_start, quiet_end):
        return t

    if quiet_start > quiet_end:
        if t.hour >= quiet_start:
            # Past quiet_start -> delivery tomorrow at quiet_end
            tomorrow = t.date() + timedelta(days=1)
            return datetime(
                year=tomorrow.year,
                month=tomorrow.month,
                day=tomorrow.day,
                hour=quiet_end,
                minute=0,
                second=0,
                microsecond=0,
                tzinfo=t.tzinfo or UTC,
            )
        else:
            # After midnight, before quiet_end -> delivery today at quiet_end
            return datetime(
                year=t.year,
                month=t.month,
                day=t.day,
                hour=quiet_end,
                minute=0,
                second=0,
                microsecond=0,
                tzinfo=t.tzinfo or UTC,
            )
    else:
        # Same day quiet hours
        return datetime(
            year=t.year,
            month=t.month,
            day=t.day,
            hour=quiet_end,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=t.tzinfo or UTC,
        )
