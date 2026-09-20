"""Fields computed at query/export time rather than stored, so they never go
stale relative to "today" (see plan: Data model). Used by both the UI grids
and the Excel export sheet builders.
"""

from __future__ import annotations

from datetime import date, datetime

from app.core.enums import TERMINAL_STATUSES
from app.core.models import Opportunity

FOLLOW_UP_DAYS_THRESHOLD = 10


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def days_since_application(opp: Opportunity, today: date | None = None) -> int | None:
    applied = _parse_date(opp.date_applied)
    if not applied:
        return None
    return ((today or date.today()) - applied).days


def deadline_urgency(opp: Opportunity, today: date | None = None) -> str:
    deadline = _parse_date(opp.application_deadline)
    if not deadline:
        return "No deadline"
    days_left = (deadline - (today or date.today())).days
    if days_left < 0:
        return "Critical"
    if days_left <= 3:
        return "Critical"
    if days_left <= 10:
        return "Soon"
    return "Normal"


def deadline_passed(opp: Opportunity, today: date | None = None) -> bool:
    deadline = _parse_date(opp.application_deadline)
    if not deadline:
        return False
    return deadline < (today or date.today())


def follow_up_recommended(opp: Opportunity, has_contact: bool, today: date | None = None) -> bool:
    if opp.status in TERMINAL_STATUSES or opp.status in ("Saved", "Interested", "Offer", "Accepted"):
        return False
    days = days_since_application(opp, today)
    if days is None:
        return False
    return days >= FOLLOW_UP_DAYS_THRESHOLD and has_contact


def application_health(opp: Opportunity, today: date | None = None) -> str:
    if opp.status in TERMINAL_STATUSES:
        return "Active"  # closed items aren't "stale," they're just done

    if deadline_passed(opp, today) and opp.status in ("Saved", "Interested", "Preparing"):
        return "Stale"

    days = days_since_application(opp, today)
    if days is not None and days >= 21:
        return "Needs action"

    urgency = deadline_urgency(opp, today)
    if urgency == "Critical":
        return "Needs action"

    return "Active"
