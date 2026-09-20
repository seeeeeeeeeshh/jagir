"""Ties the LinkedIn scraper, dedupe matcher, and merge engine together into
one sync run. This is what app/ui/pages/sync_page.py calls.

The `scraper` parameter defaults to app.sync.linkedin_scraper but accepts
any object exposing the same functions — tests inject a fake with canned
data so the whole orchestration flow (budgeting, matching, error isolation,
counts) is verified without a browser or a real LinkedIn session.
"""

from __future__ import annotations

import json
import logging
import random
import sqlite3
import time
from dataclasses import asdict
from types import ModuleType

from app.config import Settings
from app.core.models import SyncRun
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.duplicate_candidates_repo import DuplicateCandidatesRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.db.repositories.raw_snapshots_repo import RawSnapshotsRepo
from app.db.repositories.sync_runs_repo import SyncRunsRepo
from app.core.errors import humanize_exception
from app.dedupe.apply import apply_scraped_job
from app.sync import linkedin_scraper as _default_scraper
from app.sync.scraped_types import ScrapedJobListRow

logger = logging.getLogger(__name__)


def run_sync(
    conn: sqlite3.Connection,
    settings: Settings,
    on_progress: "callable | None" = None,
    scraper: ModuleType = _default_scraper,
) -> SyncRun:
    opp_repo = OpportunitiesRepo(conn)
    company_repo = CompaniesRepo(conn)
    dup_repo = DuplicateCandidatesRepo(conn)
    snapshots_repo = RawSnapshotsRepo(conn)
    sync_runs_repo = SyncRunsRepo(conn)

    def progress(msg: str) -> None:
        logger.info(msg)
        if on_progress:
            on_progress(msg)

    run = sync_runs_repo.start()
    errors: list[str] = []

    progress("Opening browser…")
    pw, context = None, None
    close_browser_on_exit = True
    try:
        pw, context = scraper.launch_browser(settings.browser_profile_abs_dir, settings.browser_headless)
        page = context.new_page()

        if not scraper.ensure_logged_in(context, page):
            # Leave the browser open on the LinkedIn page so the user can log
            # in by hand right now, in the same window — closing it here
            # would defeat the point of surfacing this at all.
            close_browser_on_exit = False
            run.status = "failed"
            run.summary_text = (
                "Not logged in to LinkedIn — log in in the browser window that just opened, "
                "then close that window and click Sync again."
            )
            run.errors_json = json.dumps([run.summary_text])
            return sync_runs_repo.finish(run)

        progress("Scraping saved jobs…")
        saved_rows = _safe_scrape(lambda: scraper.scrape_saved_jobs_list(page, settings.max_items_per_list), errors)
        _pace(settings)
        progress("Scraping applied jobs…")
        applied_rows = _safe_scrape(lambda: scraper.scrape_applied_jobs_list(page, settings.max_items_per_list), errors)

        all_rows: list[tuple[ScrapedJobListRow, str]] = (
            [(r, "saved") for r in saved_rows] + [(r, "applied") for r in applied_rows]
        )

        detail_budget = settings.max_detail_fetches_per_run
        prioritized = _prioritize_for_detail(all_rows, opp_repo)

        details_by_url: dict[str, object] = {}
        for row, _list_type in prioritized[:detail_budget]:
            if not row.linkedin_url:
                continue
            _pace(settings)
            progress(f"Fetching detail for {row.title[:40]}…")
            detail = _safe_scrape(lambda r=row: scraper.scrape_job_detail(page, r.linkedin_url), errors)
            if detail is not None:
                details_by_url[row.linkedin_url] = detail

        for row, list_type in all_rows:
            try:
                scraped = scraper.to_scraped_job(row, details_by_url.get(row.linkedin_url))
                apply_scraped_job(scraped, list_type, run, opp_repo, company_repo, dup_repo)
            except Exception as exc:  # one bad record must not abort the whole run
                errors.append(f"{row.title}: {humanize_exception(exc)}")
                if settings.raw_snapshot_mode in ("errors_and_debug", "every_sync"):
                    snapshots_repo.save(run.id, page_type=f"{list_type}_list_row_error", raw_content=str(exc), url=row.linkedin_url)

        if settings.raw_snapshot_mode == "every_sync":
            for row, list_type in all_rows:
                snapshots_repo.save(run.id, page_type=f"{list_type}_list_row", raw_content=json.dumps(asdict(row)), url=row.linkedin_url)

        snapshots_repo.prune_older_than(settings.raw_snapshot_retention_days)

        run.status = "partial" if errors else "success"
        run.errors_json = json.dumps(errors) if errors else None
        run.summary_text = (
            f"{run.new_saved_count} new saved, {run.new_applied_count} new applied, "
            f"{run.updated_count} updated, {run.duplicates_flagged_count} flagged for review"
            + (f" — {len(errors)} error(s)" if errors else "")
        )
        return sync_runs_repo.finish(run)

    except Exception as exc:
        logger.exception("Sync run failed")  # full detail stays in the log; the run record gets the human version
        run.status = "failed"
        run.errors_json = json.dumps([str(exc)])
        run.summary_text = f"Sync failed: {humanize_exception(exc)}"
        return sync_runs_repo.finish(run)

    finally:
        if context is not None and close_browser_on_exit and not settings.keep_browser_open:
            scraper.close_browser(pw, context)


def _pace(settings: Settings) -> None:
    """A randomized pause between page actions so a sync reads as occasional
    manual browsing rather than a bot hammering the site at machine speed."""
    time.sleep(random.uniform(settings.action_delay_min_seconds, settings.action_delay_max_seconds))


def _safe_scrape(fn, errors: list[str]):
    try:
        return fn()
    except Exception as exc:
        errors.append(humanize_exception(exc))
        return None


def _prioritize_for_detail(
    rows: list[tuple[ScrapedJobListRow, str]], opp_repo: OpportunitiesRepo
) -> list[tuple[ScrapedJobListRow, str]]:
    """Spends the limited detail-fetch budget on rows most likely to need
    it: brand-new records first, then existing records with the stalest
    (or no) prior sync timestamp."""

    def sort_key(item: tuple[ScrapedJobListRow, str]):
        row, _ = item
        existing = opp_repo.find_by_linkedin_job_id(row.linkedin_job_id) if row.linkedin_job_id else None
        if existing is None:
            return (0, "")
        return (1, existing.linkedin_last_synced_at or "")

    return sorted(rows, key=sort_key)
