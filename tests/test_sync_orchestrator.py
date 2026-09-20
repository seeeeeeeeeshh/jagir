"""Exercises the sync orchestration flow (budgeting, matching, error
isolation, run counts) with a fake scraper injected in place of Playwright
— no browser, no real LinkedIn session needed. Real selector validation
against LinkedIn's live DOM is a separate, manual follow-up (see
app/sync/linkedin_scraper.py's module docstring)."""

from types import SimpleNamespace

from app.core.models import Opportunity
from app.core.enums import DUPLICATE_CANDIDATE_STATUS_OPTIONS  # noqa: F401  (documents expected status vocabulary)
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.duplicate_candidates_repo import DuplicateCandidatesRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.sync.scraped_types import ScrapedJob, ScrapedJobListRow
from app.sync.sync_orchestrator import run_sync


def _row(**overrides) -> ScrapedJobListRow:
    defaults = dict(
        linkedin_job_id="1",
        linkedin_url="https://linkedin.com/jobs/view/1",
        title="Software Engineer Intern",
        company_name="Acme Inc.",
        location="Remote",
    )
    defaults.update(overrides)
    return ScrapedJobListRow(**defaults)


def _fake_scraper(saved_rows=None, applied_rows=None, logged_in=True, detail_error_for: set[str] | None = None):
    saved_rows = saved_rows or []
    applied_rows = applied_rows or []
    detail_error_for = detail_error_for or set()

    def scrape_job_detail(page, job_url):
        if job_url in detail_error_for:
            raise TimeoutError("simulated timeout")
        return None

    def to_scraped_job(list_row, detail):
        return ScrapedJob(
            linkedin_job_id=list_row.linkedin_job_id,
            linkedin_url=list_row.linkedin_url,
            canonical_linkedin_url=list_row.linkedin_url,
            title=list_row.title,
            company_name=list_row.company_name,
            location=list_row.location,
            date_applied=list_row.date_applied,
            date_saved=list_row.date_saved,
        )

    fake_page = SimpleNamespace()
    fake_context = SimpleNamespace(new_page=lambda: fake_page)

    return SimpleNamespace(
        launch_browser=lambda profile_dir, headless: (object(), fake_context),
        close_browser=lambda pw, context: None,
        ensure_logged_in=lambda context, page: logged_in,
        scrape_saved_jobs_list=lambda page, max_items: saved_rows[:max_items],
        scrape_applied_jobs_list=lambda page, max_items: applied_rows[:max_items],
        scrape_job_detail=scrape_job_detail,
        to_scraped_job=to_scraped_job,
    )


def _fake_settings():
    from app.config import Settings

    return Settings(
        database_path=":memory:",
        browser_profile_dir="unused",
        browser_headless=True,
        keep_browser_open=False,
        raw_snapshot_mode="none",
        max_items_per_list=50,
        max_detail_fetches_per_run=5,
        action_delay_min_seconds=0,
        action_delay_max_seconds=0,
    )


def test_run_sync_creates_new_record(conn):
    scraper = _fake_scraper(saved_rows=[_row()])
    run = run_sync(conn, _fake_settings(), scraper=scraper)

    assert run.status == "success"
    assert run.new_saved_count == 1
    opps = OpportunitiesRepo(conn).list_all()
    assert len(opps) == 1
    assert opps[0].origin == "linkedin_import"
    assert opps[0].linkedin_job_id == "1"


def test_run_sync_updates_existing_exact_match(conn):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    opps.create(Opportunity(title="Old Title", company_id=company.id, linkedin_job_id="1", status="Interview 1"))

    scraper = _fake_scraper(saved_rows=[_row(title="New Title From LinkedIn")])
    run = run_sync(conn, _fake_settings(), scraper=scraper)

    assert run.status == "success"
    assert run.updated_count == 1
    updated = opps.list_all()[0]
    assert updated.title == "New Title From LinkedIn"
    assert updated.status == "Interview 1"  # user-owned field untouched


def test_run_sync_flags_fuzzy_duplicate(conn):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    existing = opps.create(Opportunity(title="Software Engineer Intern", company_id=company.id, origin="manual"))

    scraper = _fake_scraper(saved_rows=[_row(linkedin_job_id=None, linkedin_url=None, title="Software Engineering Intern")])
    run = run_sync(conn, _fake_settings(), scraper=scraper)

    assert run.status == "success"
    assert run.duplicates_flagged_count == 1
    candidates = DuplicateCandidatesRepo(conn).list_pending()
    assert len(candidates) == 1
    assert candidates[0].candidate_opportunity_id == existing.id
    refreshed = opps.get(existing.id)
    assert refreshed.needs_review == 1


def test_run_sync_not_logged_in_makes_no_db_writes(conn):
    scraper = _fake_scraper(saved_rows=[_row()], logged_in=False)
    run = run_sync(conn, _fake_settings(), scraper=scraper)

    assert run.status == "failed"
    assert OpportunitiesRepo(conn).list_all() == []


def test_run_sync_isolates_per_record_errors(conn):
    good = _row(linkedin_job_id="1", linkedin_url="https://linkedin.com/jobs/view/1", title="Good Row")
    bad = _row(linkedin_job_id="2", linkedin_url="https://linkedin.com/jobs/view/2", title="Bad Row")
    scraper = _fake_scraper(saved_rows=[good, bad])

    def to_scraped_job(list_row, detail):
        if list_row.title == "Bad Row":
            raise ValueError("simulated parse failure")
        return ScrapedJob(
            linkedin_job_id=list_row.linkedin_job_id,
            linkedin_url=list_row.linkedin_url,
            canonical_linkedin_url=list_row.linkedin_url,
            title=list_row.title,
            company_name=list_row.company_name,
        )

    scraper.to_scraped_job = to_scraped_job
    run = run_sync(conn, _fake_settings(), scraper=scraper)

    assert run.status == "partial"
    assert run.new_saved_count == 1
    assert "Bad Row" in (run.errors_json or "")
    assert len(OpportunitiesRepo(conn).list_all()) == 1
