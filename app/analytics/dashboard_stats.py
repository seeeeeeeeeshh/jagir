"""Full analytics for the Dashboard page: stage distribution, outcomes,
time-to-response, and company/position-type breakdowns.

Excel's Dashboard sheet (app/excel/sheet_builders/dashboard_sheet.py) is
deliberately minimal and predates this; the two are allowed to differ.

Funnel is a CURRENT-status distribution, not a true historical funnel: we
only know each opportunity's current status, not the sequence of statuses
it passed through, so we can't say a since-rejected application reached
"Interview" before being rejected. Terminal outcomes (Accepted/Rejected/
Withdrawn/Ghosted) and On Hold are reported separately rather than forced
into the linear funnel, for the same reason. This is the same limitation
app/excel/sheet_builders/companies_sheet.py already has (its "Interviews"
column is also a current-status bucket, not a historical count) — this
module stays consistent with that existing precedent rather than diverging.
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass
from datetime import date, datetime

from app.core.enums import PRE_APPLICATION_STATUSES
from app.core.models import Opportunity
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.interviews_repo import InterviewsRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo

_FUNNEL_STAGES: list[tuple[str, set[str]]] = [
    ("Saved", {"Saved", "Interested"}),
    ("Applied", {"Applied", "Preparing"}),
    ("Screening", {"OA", "Recruiter Screen"}),
    ("Interviewing", {"Interview 1", "Interview 2"}),
    ("Final Round", {"Final Round"}),
    ("Offer", {"Offer"}),
]

_OUTCOME_STAGES: list[tuple[str, set[str]]] = [
    ("Accepted", {"Accepted"}),
    ("Rejected", {"Rejected"}),
    ("Withdrawn", {"Withdrawn"}),
    ("Ghosted", {"Ghosted"}),
    ("On Hold", {"On Hold"}),
]

_INTERVIEWED_STATUSES = {
    "OA", "Recruiter Screen", "Interview 1", "Interview 2", "Final Round", "Offer", "Accepted",
}


@dataclass
class StageCount:
    label: str
    count: int


@dataclass
class TimeToResponseStats:
    median_days: float | None
    average_days: float | None
    sample_size: int


@dataclass
class CompanyStats:
    name: str
    opportunities: int
    applications: int
    interviews: int
    offers: int
    rejections: int


@dataclass
class PositionTypeStats:
    position_type: str
    count: int
    offers: int


@dataclass
class DashboardAnalytics:
    funnel: list[StageCount]
    outcomes: list[StageCount]
    time_to_response: TimeToResponseStats
    by_company: list[CompanyStats]
    by_position_type: list[PositionTypeStats]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def compute_funnel(opps: list[Opportunity]) -> list[StageCount]:
    return [StageCount(label, sum(1 for o in opps if o.status in statuses)) for label, statuses in _FUNNEL_STAGES]


def compute_outcomes(opps: list[Opportunity]) -> list[StageCount]:
    return [StageCount(label, sum(1 for o in opps if o.status in statuses)) for label, statuses in _OUTCOME_STAGES]


def compute_time_to_response(conn: sqlite3.Connection, opps: list[Opportunity]) -> TimeToResponseStats:
    """Days between applying and the earliest interview scheduled for that
    opportunity. Uses the interviews table's own scheduled_at directly,
    rather than mining free-text activity-log descriptions for
    status-change history, which is a fragile source for this."""
    interviews_repo = InterviewsRepo(conn)
    deltas: list[int] = []
    for o in opps:
        applied = _parse_date(o.date_applied)
        if not applied:
            continue
        scheduled_dates = [d for d in (_parse_date(i.scheduled_at) for i in interviews_repo.list_for_opportunity(o.id)) if d]
        if not scheduled_dates:
            continue
        delta = (min(scheduled_dates) - applied).days
        if delta >= 0:
            deltas.append(delta)
    if not deltas:
        return TimeToResponseStats(None, None, 0)
    return TimeToResponseStats(
        median_days=statistics.median(deltas), average_days=sum(deltas) / len(deltas), sample_size=len(deltas)
    )


def compute_company_breakdown(conn: sqlite3.Connection, opps: list[Opportunity], limit: int = 8) -> list[CompanyStats]:
    companies_by_id = {c.id: c for c in CompaniesRepo(conn).list_all()}
    stats: dict[int, CompanyStats] = {}
    for o in opps:
        key = o.company_id or 0
        if key not in stats:
            company = companies_by_id.get(o.company_id)
            stats[key] = CompanyStats(
                name=company.name if company else "Unknown", opportunities=0, applications=0,
                interviews=0, offers=0, rejections=0,
            )
        s = stats[key]
        s.opportunities += 1
        # date_applied is frequently never captured (LinkedIn list pages
        # don't expose it) — Status reliably is, so "left the
        # pre-application stage" is what actually means "applied" here.
        # Same bug, same fix, as companies_sheet.py/companies_page.py.
        if o.status not in PRE_APPLICATION_STATUSES:
            s.applications += 1
        if o.status in _INTERVIEWED_STATUSES:
            s.interviews += 1
        if o.status in ("Offer", "Accepted"):
            s.offers += 1
        if o.status == "Rejected":
            s.rejections += 1
    ranked = sorted(stats.values(), key=lambda s: s.opportunities, reverse=True)
    return ranked[:limit]


def compute_position_type_breakdown(opps: list[Opportunity]) -> list[PositionTypeStats]:
    stats: dict[str, PositionTypeStats] = {}
    for o in opps:
        key = o.position_type or "Unknown"
        if key not in stats:
            stats[key] = PositionTypeStats(position_type=key, count=0, offers=0)
        stats[key].count += 1
        if o.status in ("Offer", "Accepted"):
            stats[key].offers += 1
    return sorted(stats.values(), key=lambda s: s.count, reverse=True)


def compute_dashboard_analytics(conn: sqlite3.Connection, cycle_id: int | None = None) -> DashboardAnalytics:
    opps = OpportunitiesRepo(conn).list_all(cycle_id=cycle_id)
    return DashboardAnalytics(
        funnel=compute_funnel(opps),
        outcomes=compute_outcomes(opps),
        time_to_response=compute_time_to_response(conn, opps),
        by_company=compute_company_breakdown(conn, opps),
        by_position_type=compute_position_type_breakdown(opps),
    )
