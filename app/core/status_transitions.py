"""The one rule that applies every time an opportunity's status changes,
wherever that happens (the detail page, bulk-edit, or an inline grid edit):
moving out of a pre-application status for the first time stamps today as
the date applied — the same thing a LinkedIn "saved job later applied to"
sync match already does. Kept in one place so the three UI call sites
can't drift into different behavior.
"""

from __future__ import annotations

from datetime import date

from app.core.enums import PRE_APPLICATION_STATUSES
from app.core.models import Opportunity


def apply_status_change(opp: Opportunity, new_status: str) -> bool:
    """Mutates opp.status (and opp.date_applied, the first time only) in
    place. Returns True if date_applied was newly stamped, so callers can
    log/notify accordingly."""
    stamped = False
    if new_status not in PRE_APPLICATION_STATUSES and not opp.date_applied:
        opp.date_applied = date.today().isoformat()
        stamped = True
    opp.status = new_status
    return stamped
