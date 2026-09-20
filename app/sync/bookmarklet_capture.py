"""Applies job listings captured by the LinkedIn bookmarklet (see
app/api/linkedin_capture.py for the receiving HTTP route, and
app/ui/pages/sync_page.py for where the bookmarklet itself is generated).

The bookmarklet runs inside the user's own already-logged-in LinkedIn tab
and posts a plain JSON array of what's currently rendered on a saved-jobs
or applied-jobs list page — no browser automation, no persistent profile,
no separate login. This only ever captures list-level fields (title,
company, location, job id/url, and — approximate, parsed client-side from
LinkedIn's own relative-time text like "Applied 1w ago" — date_applied and
posting_date); there is no detail-page enrichment in v1, matching the same
"None means not captured this pass" contract merge.py already relies on.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import fields

from app.core.models import SyncRun
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.duplicate_candidates_repo import DuplicateCandidatesRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.db.repositories.sync_runs_repo import SyncRunsRepo
from app.dedupe.apply import apply_scraped_job
from app.sync.linkedin_scraper import canonicalize_linkedin_url, extract_job_id_from_url
from app.sync.scraped_types import ScrapedJob

_SCRAPED_JOB_FIELDS = {f.name for f in fields(ScrapedJob)}


class CaptureError(ValueError):
    """A malformed capture item — reported back to the confirmation page,
    never allowed to abort the rest of the batch."""


def _item_to_scraped_job(item: dict) -> ScrapedJob:
    title = (item.get("title") or "").strip()
    company_name = (item.get("company_name") or "").strip()
    if not title or not company_name:
        raise CaptureError(f"missing title/company in captured item: {item!r}")

    linkedin_url = item.get("linkedin_url") or None
    canonical_url = canonicalize_linkedin_url(linkedin_url) if linkedin_url else None
    linkedin_job_id = item.get("linkedin_job_id") or (extract_job_id_from_url(linkedin_url) if linkedin_url else None)

    fields_in = {
        "linkedin_job_id": linkedin_job_id,
        "linkedin_url": linkedin_url,
        "canonical_linkedin_url": canonical_url,
        "title": title,
        "company_name": company_name,
        "location": item.get("location") or None,
        "date_applied": item.get("date_applied") or None,
        "date_saved": item.get("date_saved") or None,
        "posting_date": item.get("posting_date") or None,
        "application_status_shown": item.get("application_status_shown") or None,
        "raw_metadata": {},
    }
    return ScrapedJob(**{k: v for k, v in fields_in.items() if k in _SCRAPED_JOB_FIELDS})


def capture_jobs(conn: sqlite3.Connection, items: list[dict]) -> SyncRun:
    """`items` is the bookmarklet's raw JSON payload: a list of
    `{title, company_name, location, linkedin_url, linkedin_job_id,
    list_type, date_applied}` dicts. `list_type` is "saved" or "applied",
    set by the bookmarklet from the page URL it ran on."""
    opp_repo = OpportunitiesRepo(conn)
    company_repo = CompaniesRepo(conn)
    dup_repo = DuplicateCandidatesRepo(conn)
    sync_runs_repo = SyncRunsRepo(conn)

    run = sync_runs_repo.start()
    errors: list[str] = []

    for item in items:
        try:
            scraped = _item_to_scraped_job(item)
            list_type = item.get("list_type") or "saved"
            apply_scraped_job(scraped, list_type, run, opp_repo, company_repo, dup_repo)
        except Exception as exc:  # one bad record must not abort the whole batch
            errors.append(str(exc))

    run.status = "partial" if errors else "success"
    run.errors_json = json.dumps(errors) if errors else None
    run.summary_text = (
        f"{run.new_saved_count} new saved, {run.new_applied_count} new applied, "
        f"{run.updated_count} updated, {run.duplicates_flagged_count} flagged for review"
        + (f" — {len(errors)} error(s)" if errors else "")
    )
    return sync_runs_repo.finish(run)
