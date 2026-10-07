"""The lab's clock: US East Coast (America/New_York) wall-clock time.

Lab-facing dates and times -- dish creation and termination dates, check and
event times, form defaults, "checked today", dpf -- are lab wall-clock values
stored without an offset (docs/zebrobot_snapshot.md, "Dates and times"). They
come from here, not from the host's timezone, so a server or container set to
UTC can't shift them. Internal bookkeeping stamps (cache refresh times, retry
timers) only compare against each other and may keep using the host clock.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

LAB_TIMEZONE = ZoneInfo("America/New_York")


def lab_now() -> datetime:
    """Current lab wall-clock time, naive (the form the app stores)."""
    return datetime.now(LAB_TIMEZONE).replace(tzinfo=None)


def lab_today() -> date:
    """Current lab calendar date."""
    return datetime.now(LAB_TIMEZONE).date()


def lab_calendar_date(instant: Optional[datetime] = None) -> date:
    """Lab calendar date of ``instant`` (default: now).

    Naive instants are taken as UTC; aware ones are converted.
    """
    if instant is None:
        return lab_today()
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(LAB_TIMEZONE).date()
