"""Dashboard sheet data. Deliberately minimal for now — totals and a status
breakdown only. Full funnel/conversion and time-to-response analytics land in
a later build phase (see app/analytics/); this keeps pace with what the
NiceGUI Dashboard page currently shows so the two don't drift apart.
"""

import sqlite3

import pandas as pd

from app.core.enums import PRE_APPLICATION_STATUSES, RESEARCH_POSITION_TYPES, STATUS_OPTIONS
from app.db.repositories.opportunities_repo import OpportunitiesRepo


def build_dashboard_stats(conn: sqlite3.Connection) -> pd.DataFrame:
    opps = OpportunitiesRepo(conn).list_all()
    total = len(opps)
    saved = sum(1 for o in opps if o.status in PRE_APPLICATION_STATUSES)
    applied = total - saved
    research = sum(1 for o in opps if o.position_type in RESEARCH_POSITION_TYPES)
    offers = sum(1 for o in opps if o.status in ("Offer", "Accepted"))
    needs_review = sum(1 for o in opps if o.needs_review)

    rows = [
        ("Total opportunities", total),
        ("Saved (not yet applied)", saved),
        ("Applications in pipeline", applied),
        ("Research / RA", research),
        ("Offers", offers),
        ("Needs review (possible duplicates)", needs_review),
    ]
    return pd.DataFrame(rows, columns=["Metric", "Value"])


def build_status_breakdown(conn: sqlite3.Connection) -> pd.DataFrame:
    opps = OpportunitiesRepo(conn).list_all()
    counts = {status: 0 for status in STATUS_OPTIONS}
    for o in opps:
        counts[o.status] = counts.get(o.status, 0) + 1
    rows = [(status, count) for status, count in counts.items() if count > 0]
    if not rows:
        rows = [(status, 0) for status in STATUS_OPTIONS[:1]]
    return pd.DataFrame(rows, columns=["Status", "Count"])
