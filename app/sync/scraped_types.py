"""Selector-agnostic payload types the scraper hands to the matcher/merge
engine. Nothing outside app/sync/linkedin_scraper.py should ever know about
CSS selectors or Playwright objects — everything downstream of this module
works with these plain dataclasses, which is what keeps the matcher, merge,
and orchestrator fully unit-testable without a browser.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScrapedJobListRow:
    """One row from a LinkedIn saved-jobs or applied-jobs list page — cheap
    to get in bulk, no full description."""

    linkedin_job_id: str | None
    linkedin_url: str | None
    title: str
    company_name: str
    location: str | None = None
    date_saved: str | None = None
    date_applied: str | None = None
    posting_date: str | None = None
    application_status_shown: str | None = None


@dataclass
class ScrapedJobDetail:
    """Fields only available from a job's own detail page — expensive
    (one page load each), so the orchestrator budgets these."""

    workplace_type: str | None = None
    employment_type: str | None = None
    salary_text: str | None = None
    job_description: str | None = None
    posting_date: str | None = None
    easy_apply: int | None = None
    external_apply_url: str | None = None
    recruiter_name: str | None = None
    raw_metadata: dict = field(default_factory=dict)


@dataclass
class ScrapedJob:
    """The matcher/merge engine's input: a list row optionally enriched with
    detail-page data. Field names match `Opportunity` attributes 1:1 so
    mapping stays trivial. A field left `None` means "not captured this
    run" (e.g. a list-only pass), never "clear the existing value" — merge.py
    depends on that distinction.
    """

    linkedin_job_id: str | None
    linkedin_url: str | None
    canonical_linkedin_url: str | None
    title: str
    company_name: str
    location: str | None = None
    workplace_type: str | None = None
    employment_type: str | None = None
    salary_text: str | None = None
    job_description: str | None = None
    date_applied: str | None = None
    date_saved: str | None = None
    posting_date: str | None = None
    easy_apply: int | None = None
    external_apply_url: str | None = None
    application_status_shown: str | None = None
    recruiter_name: str | None = None
    raw_metadata: dict = field(default_factory=dict)
