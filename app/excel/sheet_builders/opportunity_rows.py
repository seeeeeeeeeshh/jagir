"""Shared row-building logic for every sheet that's fundamentally a view over
`opportunities` (All Opportunities, Applications, Research, Saved Jobs).
One function here == one column list, so the four sheets can never drift
apart in what a column means (see plan: single canonical field per fact).
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd

from app.analytics.derived_fields import application_health, deadline_urgency
from app.core.models import Opportunity
from app.db.repositories.cycles_repo import CyclesRepo

# Trimmed against real usage, not guessed: across every real record in this
# app, Hiring Manager/Referral Contact/Networking Status/Last Contacted/
# Next Follow-up/Internship Start-End Date/Cover Letter Version/Employment
# Type/External Application URL/Origin were 0% filled and none of them have
# an editing surface anywhere in the app's own UI (Excel was the only way
# to touch them) — dead columns, not just quiet ones. Latest Interview
# Stage/Date is dropped too: it's redundant with Status plus the full
# per-interview history already on the Interviews sheet, and it required a
# per-row Interviews query for information the sheet already carries.
# Rejection Date and Withdrawal Date are dropped in favor of just Offer
# Date — the one outcome date that's actually time-sensitive and
# decision-relevant day to day. "Had OA / Technical / Behavioral / Final
# Round" columns were already dropped in an earlier pass for the same
# reason. "Days Since Application" is intentionally NOT computed here —
# export.py writes it as a live Excel formula off "Date Applied" instead,
# so it stays current without a re-export.
COLUMNS = [
    "Application ID", "Company", "Role", "Position Type", "Cycle", "Location", "Workplace",
    "Job URL", "Source",
    "Date Saved", "Date Applied", "Deadline", "Status", "Priority",
    "Target / Reach / Safety",
    "Compensation", "Recruiter", "Offer Date", "Days Since Application",
    "Urgency", "Application Health", "Next Action", "Notes", "Resume Version",
    "Last Updated",
]

# Plain "YYYY-MM-DD" fields written as real Excel dates (not text) so they
# sort/filter properly in Excel and the Days-Since-Application formula can
# do date arithmetic on them.
_DATE_FIELDS = {
    "Date Saved": "date_saved",
    "Date Applied": "date_applied",
    "Deadline": "application_deadline",
    "Offer Date": "offer_date",
}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None  # a malformed value becomes a blank cell, not a crash


def opportunity_row(conn: sqlite3.Connection, o: Opportunity, company_name: str, cycle_name: str = "") -> dict:
    row = {
        "Application ID": o.id,
        "Company": company_name,
        "Role": o.title,
        "Position Type": o.position_type,
        "Cycle": cycle_name,
        "Location": o.location or "",
        "Workplace": o.workplace_type or "",
        "Job URL": o.job_url or o.linkedin_url or "",
        "Source": o.source,
        "Date Saved": _parse_date(o.date_saved),
        "Date Applied": _parse_date(o.date_applied),
        "Deadline": _parse_date(o.application_deadline),
        "Status": o.status,
        "Priority": o.priority or "",
        "Target / Reach / Safety": o.target_reach_safety or "",
        "Compensation": o.salary_text or "",
        "Recruiter": o.recruiter_name or "",
        "Offer Date": _parse_date(o.offer_date),
        "Days Since Application": None,  # filled in by export.py as a live formula
        "Urgency": deadline_urgency(o),
        "Application Health": application_health(o),
        "Next Action": o.next_action or "",
        "Notes": o.notes or "",
        "Resume Version": o.resume_version or "",
        "Last Updated": o.updated_at or "",
    }
    return row


def opportunities_to_dataframe(conn: sqlite3.Connection, opportunities: list[Opportunity], companies_by_id: dict) -> pd.DataFrame:
    cycles_by_id = {c.id: c.name for c in CyclesRepo(conn).list_all()}
    rows = [
        opportunity_row(
            conn,
            o,
            companies_by_id.get(o.company_id).name if o.company_id in companies_by_id else "",
            cycles_by_id.get(o.cycle_id, ""),
        )
        for o in opportunities
    ]
    return pd.DataFrame(rows, columns=COLUMNS)
