"""One-line summary of a cycle's outcome, for the Cycles page. Definitions
match the Dashboard's (same status buckets), so a cycle's numbers here equal
what the Dashboard shows while that cycle is selected."""

from __future__ import annotations

from dataclasses import dataclass

from app.analytics.dashboard_stats import _INTERVIEWED_STATUSES
from app.core.enums import PRE_APPLICATION_STATUSES
from app.core.models import Opportunity


@dataclass
class CycleSummary:
    total: int
    applied: int
    interviewed: int
    offers: int
    rejected: int
    still_open: int  # applied and not yet resolved — what archiving would set aside


_RESOLVED = {"Accepted", "Rejected", "Withdrawn", "Ghosted"}


def summarize_cycle(opps: list[Opportunity]) -> CycleSummary:
    applied = [o for o in opps if o.status not in PRE_APPLICATION_STATUSES]
    return CycleSummary(
        total=len(opps),
        applied=len(applied),
        interviewed=sum(1 for o in opps if o.status in _INTERVIEWED_STATUSES),
        offers=sum(1 for o in opps if o.status in ("Offer", "Accepted")),
        rejected=sum(1 for o in opps if o.status == "Rejected"),
        still_open=sum(1 for o in applied if o.status not in _RESOLVED),
    )
