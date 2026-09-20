"""Cycle naming/date presets shared by the repository (default cycle for a
brand-new database) and the "New cycle" dialog.

A cycle is one application season. The three terms mirror how internship
and research recruiting is actually scheduled: Fall (Sep-Dec), Spring
(Jan-Apr) and Summer (May-Aug). "Custom" exists in the UI for anything that
doesn't fit (e.g. a winter co-op) — it just skips the auto-filled dates.
"""

from __future__ import annotations

import calendar
from datetime import date

# term -> (first month, last month)
TERMS: dict[str, tuple[int, int]] = {
    "Spring": (1, 4),
    "Summer": (5, 8),
    "Fall": (9, 12),
}


def term_for_month(month: int) -> str:
    for term, (first, last) in TERMS.items():
        if first <= month <= last:
            return term
    raise ValueError(f"month out of range: {month}")


def cycle_name(term: str, year: int) -> str:
    return f"{term} {year}"


def term_dates(term: str, year: int) -> tuple[str, str]:
    """ISO start/end date for a term, e.g. Fall 2026 -> 2026-09-01..2026-12-31."""
    first, last = TERMS[term]
    end_day = calendar.monthrange(year, last)[1]
    return date(year, first, 1).isoformat(), date(year, last, end_day).isoformat()


def default_cycle_for(today: date) -> tuple[str, str, str]:
    """(name, start_date, end_date) of the term containing `today`."""
    term = term_for_month(today.month)
    start, end = term_dates(term, today.year)
    return cycle_name(term, today.year), start, end
