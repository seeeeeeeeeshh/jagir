from app.core.enums import PRE_APPLICATION_STATUSES
from app.core.models import Contact, DuplicateCandidate, Interview, Opportunity, PrepResource
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.contacts_repo import ContactsRepo
from app.db.repositories.duplicate_candidates_repo import DuplicateCandidatesRepo
from app.db.repositories.interviews_repo import InterviewsRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.db.repositories.prep_resources_repo import PrepResourcesRepo
from app.db.repositories.raw_snapshots_repo import RawSnapshotsRepo


def test_create_and_get_round_trip(conn):
    repo = OpportunitiesRepo(conn)
    created = repo.create(Opportunity(title="Backend Intern", status="Saved", position_type="Internship"))

    fetched = repo.get(created.id)
    assert fetched.title == "Backend Intern"
    assert fetched.status == "Saved"
    assert fetched.created_at is not None


def test_manual_and_linkedin_records_share_one_table(conn):
    repo = OpportunitiesRepo(conn)
    manual = repo.create(Opportunity(title="RA Position", origin="manual", source="university", position_type="RA"))
    linkedin = repo.create(Opportunity(title="SWE Intern", origin="linkedin_import", source="linkedin", linkedin_job_id="123"))

    all_opps = repo.list_all()
    assert {o.id for o in all_opps} == {manual.id, linkedin.id}
    # Both come back as plain Opportunity rows from the same table/repo -- no
    # separate "manual opportunities" vs "linkedin opportunities" schema.
    assert manual.origin == "manual"
    assert linkedin.origin == "linkedin_import"


def test_status_saved_to_applied_updates_same_row_not_a_new_one(conn):
    repo = OpportunitiesRepo(conn)
    opp = repo.create(Opportunity(title="Data Intern", status="Saved", date_saved="2026-01-01"))
    assert opp.status in PRE_APPLICATION_STATUSES

    opp.status = "Applied"
    opp.date_applied = "2026-01-10"
    repo.update(opp, log_event=("status", "Status changed to Applied"))

    all_opps = repo.list_all()
    assert len(all_opps) == 1  # no duplicate row created
    refreshed = repo.get(opp.id)
    assert refreshed.status == "Applied"
    assert refreshed.date_applied == "2026-01-10"
    assert refreshed.date_saved == "2026-01-01"  # not lost


def test_activity_log_records_events(conn):
    repo = OpportunitiesRepo(conn)
    opp = repo.create(Opportunity(title="ML Intern"))
    repo.log_activity(opp.id, "note", "Recruiter reached out")

    activity = repo.get_activity(opp.id)
    assert len(activity) == 2  # creation event + manual log
    assert activity[-1].description == "Recruiter reached out"


def test_company_get_or_create_is_idempotent_across_suffixes(conn):
    companies = CompaniesRepo(conn)
    a = companies.get_or_create("Acme Inc.")
    b = companies.get_or_create("ACME")

    assert a.id == b.id


def test_delete_removes_an_opportunity_with_only_its_creation_activity_log(conn):
    """Regression test: create() always logs an activity event, and the
    schema enforces a foreign key from application_activity back to
    opportunities — a naive `DELETE FROM opportunities` fails outright with
    a FOREIGN KEY constraint error for every real opportunity, not just
    ones with extra history."""
    repo = OpportunitiesRepo(conn)
    opp = repo.create(Opportunity(title="Backend Intern"))

    repo.delete(opp.id)

    assert repo.get(opp.id) is None
    assert repo.get_activity(opp.id) == []


def test_delete_removes_interviews_and_unlinks_contacts_and_prep_resources(conn):
    """Contacts and prep resources are shared/reusable records — deleting
    an opportunity must remove its interviews and its LINKS to them, but
    never the contact or prep resource itself."""
    opp_repo = OpportunitiesRepo(conn)
    interviews_repo = InterviewsRepo(conn)
    contacts_repo = ContactsRepo(conn)
    prep_repo = PrepResourcesRepo(conn)

    opp = opp_repo.create(Opportunity(title="Backend Intern"))
    interviews_repo.create(Interview(opportunity_id=opp.id, stage="Recruiter Screen"))
    contact = contacts_repo.create(Contact(name="Jane Recruiter"))
    contacts_repo.link_to_opportunity(opp.id, contact.id, role="recruiter")
    resource = prep_repo.create(PrepResource(title="LeetCode Arrays"))
    prep_repo.link_to_opportunity(opp.id, resource.id)

    opp_repo.delete(opp.id)

    assert opp_repo.get(opp.id) is None
    assert interviews_repo.list_for_opportunity(opp.id) == []
    assert contacts_repo.list_for_opportunity(opp.id) == []
    assert prep_repo.list_for_opportunity(opp.id) == []
    # the contact and prep resource themselves survive — only the link died
    assert contacts_repo.get(contact.id) is not None
    assert prep_repo.get(resource.id) is not None


def test_delete_clears_duplicate_of_id_on_other_opportunities_without_deleting_them(conn):
    opp_repo = OpportunitiesRepo(conn)
    original = opp_repo.create(Opportunity(title="Backend Intern"))
    duplicate = opp_repo.create(Opportunity(title="Backend Intern (dup)", duplicate_of_id=original.id))

    opp_repo.delete(original.id)

    refreshed = opp_repo.get(duplicate.id)
    assert refreshed is not None  # the duplicate row itself is untouched
    assert refreshed.duplicate_of_id is None  # just the dangling reference is cleared


def test_delete_removes_duplicate_candidates_and_raw_snapshots_referencing_it(conn):
    opp_repo = OpportunitiesRepo(conn)
    dup_repo = DuplicateCandidatesRepo(conn)
    snapshots_repo = RawSnapshotsRepo(conn)

    opp = opp_repo.create(Opportunity(title="Backend Intern"))
    dup_repo.create(DuplicateCandidate(new_record_payload_json="{}", candidate_opportunity_id=opp.id, status="pending"))
    snapshots_repo.save(sync_run_id=None, page_type="job_detail", raw_content="<html></html>", opportunity_id=opp.id)

    opp_repo.delete(opp.id)

    assert opp_repo.get(opp.id) is None
    assert dup_repo.list_pending() == []
    remaining_snapshots = conn.execute("SELECT COUNT(*) FROM raw_snapshots WHERE opportunity_id = ?", (opp.id,)).fetchone()[0]
    assert remaining_snapshots == 0
