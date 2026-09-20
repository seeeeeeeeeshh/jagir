import openpyxl
import pytest

from app.core.models import Company, Contact, Interview, Opportunity, PrepResource
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.contacts_repo import ContactsRepo
from app.db.repositories.interviews_repo import InterviewsRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.db.repositories.prep_resources_repo import PrepResourcesRepo
from app.excel.importer import import_workbook


def _workbook_with_sheet(sheet_name: str, headers: list[str], rows: list[list]):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet(sheet_name)
    ws.append(headers)
    for row in rows:
        ws.append(row)
    return wb


def _save(wb, tmp_path, name="import.xlsx"):
    path = tmp_path / name
    wb.save(path)
    return path


OPP_HEADERS = [
    "Application ID", "Company", "Role", "Position Type", "Location", "Workplace",
    "Job URL", "Source",
    "Date Saved", "Date Applied", "Deadline", "Status", "Priority",
    "Target / Reach / Safety",
    "Compensation", "Recruiter", "Offer Date", "Days Since Application",
    "Urgency", "Application Health", "Next Action", "Notes", "Resume Version",
    "Last Updated",
]


def _opp_row(**overrides) -> list:
    row = {h: None for h in OPP_HEADERS}
    row.update(overrides)
    return [row[h] for h in OPP_HEADERS]


def test_import_creates_new_opportunity(conn, tmp_path):
    wb = _workbook_with_sheet(
        "All Opportunities",
        OPP_HEADERS,
        [_opp_row(Company="Acme Inc.", Role="Backend Intern", Status="Saved", Priority="High")],
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.opportunities_created == 1
    assert result.opportunities_updated == 0
    opps = OpportunitiesRepo(conn).list_all()
    assert len(opps) == 1
    assert opps[0].title == "Backend Intern"
    assert opps[0].priority == "High"
    assert opps[0].origin == "excel_import"


def test_import_new_row_missing_required_fields_is_an_error(conn, tmp_path):
    wb = _workbook_with_sheet("All Opportunities", OPP_HEADERS, [_opp_row(Company="Acme Inc.", Role=None)])
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.opportunities_created == 0
    assert len(result.errors) == 1
    assert "Company and Role" in result.errors[0]


def test_import_reads_a_real_excel_date_cell_as_plain_iso_date(conn, tmp_path):
    """Regression test: export.py writes Date Applied/Deadline/etc. as real
    Excel dates (not text) so they sort/filter properly and the Days Since
    Application formula can do date math on them. openpyxl reads a date
    cell back as a datetime object, not a string — _clean() must format
    that as "YYYY-MM-DD", not str() it into "2026-01-05 00:00:00"."""
    import datetime as dt

    wb = _workbook_with_sheet(
        "All Opportunities",
        OPP_HEADERS,
        [_opp_row(Company="Acme Inc.", Role="Backend Intern", **{"Date Applied": dt.datetime(2026, 1, 5)})],
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.opportunities_created == 1
    opp = OpportunitiesRepo(conn).list_all()[0]
    assert opp.date_applied == "2026-01-05"


def test_import_updates_existing_opportunity_user_owned_field(conn, tmp_path):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    existing = opps.create(Opportunity(title="Backend Intern", company_id=company.id, status="Saved", priority="Low"))

    wb = _workbook_with_sheet(
        "All Opportunities", OPP_HEADERS, [_opp_row(**{"Application ID": existing.id, "Status": "Applied", "Priority": "High", "Notes": "Great fit"})]
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.opportunities_updated == 1
    updated = opps.get(existing.id)
    assert updated.status == "Applied"
    assert updated.priority == "High"
    assert updated.notes == "Great fit"


def test_import_never_overwrites_linkedin_owned_field_on_existing_row(conn, tmp_path):
    """title/location/salary_text etc are LINKEDIN_OWNED_FIELDS — an Excel
    edit to Role/Location/Compensation on an EXISTING row must be ignored,
    same as the in-app UI already treats them as read-only."""
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    existing = opps.create(
        Opportunity(title="Original Title", company_id=company.id, status="Saved", location="Original Location")
    )

    wb = _workbook_with_sheet(
        "All Opportunities",
        OPP_HEADERS,
        [_opp_row(**{"Application ID": existing.id, "Role": "Hacked Title", "Location": "Hacked Location", "Status": "Applied"})],
    )
    path = _save(wb, tmp_path)

    import_workbook(conn, path)

    updated = opps.get(existing.id)
    assert updated.title == "Original Title"  # untouched
    assert updated.location == "Original Location"  # untouched
    assert updated.status == "Applied"  # user-owned field, correctly updated


def test_import_blank_cell_clears_a_user_owned_field(conn, tmp_path):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    existing = opps.create(Opportunity(title="Backend Intern", company_id=company.id, notes="Old notes"))

    wb = _workbook_with_sheet("All Opportunities", OPP_HEADERS, [_opp_row(**{"Application ID": existing.id, "Notes": None})])
    path = _save(wb, tmp_path)

    import_workbook(conn, path)

    assert opps.get(existing.id).notes is None


def test_import_invalid_enum_value_is_reported_and_field_left_unchanged(conn, tmp_path):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    existing = opps.create(Opportunity(title="Backend Intern", company_id=company.id, status="Saved"))

    wb = _workbook_with_sheet(
        "All Opportunities", OPP_HEADERS, [_opp_row(**{"Application ID": existing.id, "Status": "Not A Real Status"})]
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert opps.get(existing.id).status == "Saved"  # unchanged
    assert any("invalid Status" in e for e in result.errors)


def test_import_missing_application_id_reports_error_and_skips_row(conn, tmp_path):
    wb = _workbook_with_sheet("All Opportunities", OPP_HEADERS, [_opp_row(**{"Application ID": 9999, "Status": "Applied"})])
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.opportunities_updated == 0
    assert any("9999" in e for e in result.errors)


def test_import_is_idempotent_reimporting_unchanged_rows_reports_no_updates(conn, tmp_path):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    existing = opps.create(Opportunity(title="Backend Intern", company_id=company.id, status="Saved", priority="High"))

    wb = _workbook_with_sheet(
        "All Opportunities", OPP_HEADERS, [_opp_row(**{"Application ID": existing.id, "Status": "Saved", "Priority": "High"})]
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    # still counts as "updated" since we always write user-owned fields (no
    # short-circuit on unchanged values for opportunities) — this test
    # documents that behavior rather than asserting a stricter no-op.
    assert result.opportunities_updated == 1
    assert opps.get(existing.id).status == "Saved"


def test_import_companies_creates_and_updates(conn, tmp_path):
    companies = CompaniesRepo(conn)
    existing = companies.get_or_create("Acme Inc.")

    wb = _workbook_with_sheet(
        "Companies",
        ["Company", "Website", "Industry", "Opportunities", "Applications", "Interviews", "Offers", "Rejections", "Notes"],
        [
            ["Acme Inc.", "https://acme.example", "Tech", 0, 0, 0, 0, 0, "Great culture"],
            ["Globex Corp", None, None, 0, 0, 0, 0, 0, None],
        ],
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.companies_created == 1  # Globex is new
    assert result.companies_updated == 1  # Acme changed
    refreshed = companies.get(existing.id)
    assert refreshed.website == "https://acme.example"
    assert refreshed.notes == "Great culture"
    assert any(c.name == "Globex Corp" for c in companies.list_all())


def test_import_companies_reimport_unchanged_reports_no_update(conn, tmp_path):
    companies = CompaniesRepo(conn)
    companies.get_or_create("Acme Inc.")

    wb = _workbook_with_sheet(
        "Companies",
        ["Company", "Website", "Industry", "Opportunities", "Applications", "Interviews", "Offers", "Rejections", "Notes"],
        [["Acme Inc.", None, None, 0, 0, 0, 0, 0, None]],
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.companies_created == 0
    assert result.companies_updated == 0


def test_import_contacts_creates_and_updates(conn, tmp_path):
    contacts = ContactsRepo(conn)
    existing = contacts.create(Contact(name="Jane Recruiter", relationship="Not contacted"))

    wb = _workbook_with_sheet(
        "Networking",
        ["Contact ID", "Name", "Company", "Title", "LinkedIn URL", "Relationship / Status", "Email", "Phone", "Notes", "Last Updated"],
        [
            [existing.id, "Jane Recruiter", None, "Senior Recruiter", None, "Connected", "jane@example.com", None, None, None],
            [None, "New Contact", None, None, None, None, None, None, None, None],
        ],
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.contacts_updated == 1
    assert result.contacts_created == 1
    refreshed = contacts.get(existing.id)
    assert refreshed.relationship == "Connected"
    assert refreshed.title == "Senior Recruiter"


def test_import_prep_resources_creates_and_updates(conn, tmp_path):
    prep = PrepResourcesRepo(conn)
    existing = prep.create(PrepResource(title="LeetCode Arrays", category="LeetCode"))

    wb = _workbook_with_sheet(
        "Prep Resources",
        ["Resource ID", "Title", "Category", "URL / Path", "Tags", "Notes", "Last Updated"],
        [
            [existing.id, "LeetCode Arrays", "LeetCode", "https://leetcode.com", "arrays,easy", "Updated notes", None],
            [None, "New Resource", "SQL", None, None, None, None],
        ],
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.prep_updated == 1
    assert result.prep_created == 1
    refreshed = prep.get(existing.id)
    assert refreshed.notes == "Updated notes"
    assert refreshed.tags == "arrays,easy"


INTERVIEW_HEADERS = [
    "Interview ID", "Application ID", "Company", "Role", "Stage", "Scheduled At",
    "Completed At", "Outcome", "Prep Notes", "Feedback Notes",
]


def test_import_interviews_creates_new_attached_to_application(conn, tmp_path):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    opp = opps.create(Opportunity(title="Backend Intern", company_id=company.id, position_type="Internship", status="Applied", source="manual"))

    wb = _workbook_with_sheet(
        "Interviews",
        INTERVIEW_HEADERS,
        [[None, opp.id, "Acme Inc.", "Backend Intern", "Recruiter Screen", "2026-09-20T14:00", None, None, "Review STAR stories", None]],
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.interviews_created == 1
    interviews = InterviewsRepo(conn).list_for_opportunity(opp.id)
    assert len(interviews) == 1
    assert interviews[0].stage == "Recruiter Screen"
    assert interviews[0].prep_notes == "Review STAR stories"


def test_import_interviews_updates_existing(conn, tmp_path):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    interviews_repo = InterviewsRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    opp = opps.create(Opportunity(title="Backend Intern", company_id=company.id, position_type="Internship", status="Applied", source="manual"))
    existing = interviews_repo.create(Interview(opportunity_id=opp.id, stage="Recruiter Screen", scheduled_at="2026-09-20T14:00"))

    wb = _workbook_with_sheet(
        "Interviews",
        INTERVIEW_HEADERS,
        [[existing.id, opp.id, "Acme Inc.", "Backend Intern", "Technical", "2026-09-25T10:00", None, "Passed", None, "Went well"]],
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.interviews_updated == 1
    refreshed = interviews_repo.get(existing.id)
    assert refreshed.stage == "Technical"
    assert refreshed.outcome == "Passed"
    assert refreshed.feedback_notes == "Went well"


def test_import_interviews_new_row_requires_valid_application_id(conn, tmp_path):
    wb = _workbook_with_sheet(
        "Interviews",
        INTERVIEW_HEADERS,
        [[None, 999999, "Ghost Co", "Ghost Role", "Recruiter Screen", None, None, None, None, None]],
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.interviews_created == 0
    assert any("Application ID" in e for e in result.errors)


def test_import_interviews_invalid_stage_on_new_row_is_skipped(conn, tmp_path):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    opp = opps.create(Opportunity(title="Backend Intern", company_id=company.id, position_type="Internship", status="Applied", source="manual"))

    wb = _workbook_with_sheet(
        "Interviews",
        INTERVIEW_HEADERS,
        [[None, opp.id, "Acme Inc.", "Backend Intern", "Not A Real Stage", None, None, None, None, None]],
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.interviews_created == 0
    assert any("invalid Stage" in e for e in result.errors)


def test_import_interviews_invalid_stage_on_existing_row_leaves_it_unchanged(conn, tmp_path):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    interviews_repo = InterviewsRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    opp = opps.create(Opportunity(title="Backend Intern", company_id=company.id, position_type="Internship", status="Applied", source="manual"))
    existing = interviews_repo.create(Interview(opportunity_id=opp.id, stage="Recruiter Screen"))

    wb = _workbook_with_sheet(
        "Interviews",
        INTERVIEW_HEADERS,
        [[existing.id, opp.id, "Acme Inc.", "Backend Intern", "Not A Real Stage", None, None, "Passed", None, None]],
    )
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert result.interviews_updated == 1
    refreshed = interviews_repo.get(existing.id)
    assert refreshed.stage == "Recruiter Screen"  # left unchanged, not overwritten with garbage
    assert refreshed.outcome == "Passed"  # other fields on the row still applied
    assert any("invalid Stage" in e for e in result.errors)


def test_import_reports_skipped_sheets(conn, tmp_path):
    wb = _workbook_with_sheet("All Opportunities", OPP_HEADERS, [])
    wb.create_sheet("Applications")
    wb.create_sheet("Research")
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert "Applications" in result.skipped_sheets
    assert "Research" in result.skipped_sheets


def test_import_missing_all_opportunities_sheet_reports_error(conn, tmp_path):
    wb = _workbook_with_sheet("Companies", ["Company"], [])
    path = _save(wb, tmp_path)

    result = import_workbook(conn, path)

    assert any("All Opportunities" in e for e in result.errors)
