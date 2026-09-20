"""Exercises the bookmarklet capture path end-to-end (payload parsing +
matcher + merge), independent of the HTTP layer — see
tests/test_linkedin_capture_endpoint.py for that."""

from app.core.models import Opportunity
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.duplicate_candidates_repo import DuplicateCandidatesRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.sync.bookmarklet_capture import capture_jobs


def _item(**overrides) -> dict:
    defaults = dict(
        title="Software Engineer Intern",
        company_name="Acme Inc.",
        location="Remote",
        linkedin_url="https://www.linkedin.com/jobs/view/4123456789/?trk=x",
        linkedin_job_id="4123456789",
        list_type="saved",
    )
    defaults.update(overrides)
    return defaults


def test_capture_creates_new_record(conn):
    run = capture_jobs(conn, [_item()])

    assert run.status == "success"
    assert run.new_saved_count == 1
    opps = OpportunitiesRepo(conn).list_all()
    assert len(opps) == 1
    assert opps[0].origin == "linkedin_import"
    assert opps[0].linkedin_job_id == "4123456789"
    # canonical URL derived even though the bookmarklet didn't send one directly
    assert "trk=" not in (opps[0].canonical_linkedin_url or "")


def test_capture_applied_list_type_creates_applied_status(conn):
    """Regression test: a new record's status must come from list_type
    itself, not from checking whether date_applied happens to be set —
    when the bookmarklet/extension never sent a real date_applied at all,
    that check was always false for a capture, so every new record
    silently landed as "Saved" regardless of which LinkedIn list it came
    from. Now that they do send an approximate date_applied (parsed
    client-side from LinkedIn's own "Applied 1w ago" text), list_type
    still has to be the deciding signal — a capture with no parseable date
    text must not fall back to "Saved" just because date_applied is None."""
    run = capture_jobs(conn, [_item(list_type="applied", linkedin_job_id="2", linkedin_url="https://www.linkedin.com/jobs/view/2/")])

    assert run.new_applied_count == 1
    opp = OpportunitiesRepo(conn).list_all()[0]
    assert opp.status == "Applied"


def test_capture_saved_list_type_creates_saved_status(conn):
    run = capture_jobs(conn, [_item(list_type="saved", linkedin_job_id="3", linkedin_url="https://www.linkedin.com/jobs/view/3/")])

    assert run.new_saved_count == 1
    opp = OpportunitiesRepo(conn).list_all()[0]
    assert opp.status == "Saved"


def test_capture_carries_through_date_applied_and_posting_date(conn):
    """The extension/bookmarklet now parse an approximate date_applied and
    posting_date client-side (from LinkedIn's own relative-time text) and
    send them in the capture payload — this locks in that a real value
    actually reaches the stored Opportunity, not just that the field
    exists on the dataclass."""
    run = capture_jobs(
        conn,
        [
            _item(
                list_type="applied",
                linkedin_job_id="4",
                linkedin_url="https://www.linkedin.com/jobs/view/4/",
                date_applied="2026-09-08",
                posting_date="2026-09-01",
            )
        ],
    )

    assert run.new_applied_count == 1
    opp = OpportunitiesRepo(conn).list_all()[0]
    assert opp.date_applied == "2026-09-08"
    assert opp.posting_date == "2026-09-01"


def test_capture_updates_existing_exact_match(conn):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    opps.create(Opportunity(title="Old Title", company_id=company.id, linkedin_job_id="4123456789", status="Interview 1"))

    run = capture_jobs(conn, [_item(title="New Title From Bookmarklet")])

    assert run.updated_count == 1
    updated = opps.list_all()[0]
    assert updated.title == "New Title From Bookmarklet"
    assert updated.status == "Interview 1"  # user-owned field untouched


def test_capture_flags_fuzzy_duplicate_without_identity(conn):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    existing = opps.create(Opportunity(title="Software Engineer Intern", company_id=company.id, origin="manual"))

    run = capture_jobs(
        conn, [_item(title="Software Engineering Intern", linkedin_job_id=None, linkedin_url=None)]
    )

    assert run.duplicates_flagged_count == 1
    candidates = DuplicateCandidatesRepo(conn).list_pending()
    assert candidates[0].candidate_opportunity_id == existing.id


def test_flagged_duplicate_payload_preserves_list_type_for_later_keep_both(conn):
    """list_type isn't a ScrapedJob field — it has to be stashed inside the
    stored payload for "keep both" (resolved potentially much later, in
    app/ui/components/duplicate_review_panel.py) to still know which
    LinkedIn list this came from when it creates the new record."""
    import json

    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    opps.create(Opportunity(title="Software Engineer Intern", company_id=company.id, origin="manual"))

    capture_jobs(
        conn,
        [_item(title="Software Engineering Intern", linkedin_job_id=None, linkedin_url=None, list_type="applied")],
    )

    candidate = DuplicateCandidatesRepo(conn).list_pending()[0]
    stored = json.loads(candidate.new_record_payload_json)
    assert stored["list_type"] == "applied"


def test_capture_isolates_malformed_items(conn):
    good = _item(linkedin_job_id="1", linkedin_url="https://www.linkedin.com/jobs/view/1/")
    bad = _item(title="", linkedin_job_id="2")  # missing title -> CaptureError

    run = capture_jobs(conn, [good, bad])

    assert run.status == "partial"
    assert run.new_saved_count == 1
    assert "missing title/company" in (run.errors_json or "")


def test_capture_empty_payload_succeeds_with_nothing_created(conn):
    run = capture_jobs(conn, [])

    assert run.status == "success"
    assert OpportunitiesRepo(conn).list_all() == []
