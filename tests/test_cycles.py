import sqlite3
from datetime import date
from pathlib import Path

import openpyxl
import pytest

from app.analytics.cycle_stats import summarize_cycle
from app.analytics.dashboard_stats import compute_dashboard_analytics
from app.core.cycles import default_cycle_for, term_dates, term_for_month
from app.core.models import Opportunity
from app.db.database import MIGRATIONS_DIR, run_migrations
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.cycles_repo import CyclesRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.dedupe.matcher import MatchDecision, match
from app.excel.importer import import_workbook
from app.excel.sheet_builders.opportunities_sheets import build_all_opportunities
from app.sync.scraped_types import ScrapedJob

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "app" / "db" / "schema.sql"


def _tables_and_columns(connection) -> dict[str, set[str]]:
    tables = [
        r[0]
        for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'schema_migrations'"
        )
    ]
    return {t: {r[1] for r in connection.execute(f"PRAGMA table_info({t})")} for t in tables}


# -- schema / migration ------------------------------------------------------


def test_schema_sql_matches_the_migrations():
    """schema.sql (what the tests build from) and migrations/ (what the real
    database is built from) must describe the same tables and columns, or
    every other test is verifying a schema the app never runs."""
    migrated = sqlite3.connect(":memory:")
    migrated.row_factory = sqlite3.Row
    run_migrations(migrated)

    from_schema = sqlite3.connect(":memory:")
    from_schema.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert _tables_and_columns(migrated) == _tables_and_columns(from_schema)


def test_migration_moves_existing_opportunities_into_fall_2026():
    """The real upgrade path: a database that already has opportunities
    (created before cycles existed) gets them all assigned to one cycle."""
    old = sqlite3.connect(":memory:")
    old.row_factory = sqlite3.Row
    old.executescript((MIGRATIONS_DIR / "0001_init.sql").read_text(encoding="utf-8"))
    old.execute("INSERT INTO schema_migrations VALUES ('0001_init', datetime('now'))")  # the runner records it, not the script
    for title in ("A", "B", "C"):
        old.execute(
            "INSERT INTO opportunities (title, created_at, updated_at) VALUES (?, datetime('now'), datetime('now'))",
            (title,),
        )
    old.commit()

    assert run_migrations(old) == ["0002_cycles"]

    cycles = CyclesRepo(old).list_all()
    assert [c.name for c in cycles] == ["Fall 2026"]
    assert old.execute("SELECT COUNT(*) FROM opportunities WHERE cycle_id = ?", (cycles[0].id,)).fetchone()[0] == 3
    assert CyclesRepo(old).view_cycle_id() == cycles[0].id


def test_migration_on_an_empty_database_creates_no_cycle():
    fresh = sqlite3.connect(":memory:")
    fresh.row_factory = sqlite3.Row
    run_migrations(fresh)
    assert CyclesRepo(fresh).list_all() == []


# -- term helpers ---------------------------------------------------------


def test_term_dates_and_default_cycle():
    assert term_dates("Fall", 2027) == ("2027-09-01", "2027-12-31")
    assert term_dates("Summer", 2028) == ("2028-05-01", "2028-08-31")
    assert term_dates("Spring", 2028) == ("2028-01-01", "2028-04-30")
    assert term_for_month(10) == "Fall"
    assert default_cycle_for(date(2026, 9, 20)) == ("Fall 2026", "2026-09-01", "2026-12-31")


# -- cycles repo -----------------------------------------------------------


def test_fresh_database_gets_a_default_cycle_on_first_use(conn):
    repo = CyclesRepo(conn)
    assert repo.list_all() == []
    cycle = repo.ensure_default(today=date(2027, 6, 1))
    assert cycle.name == "Summer 2027"
    assert repo.ensure_default().id == cycle.id  # idempotent


def test_duplicate_or_blank_cycle_names_are_rejected(conn):
    repo = CyclesRepo(conn)
    repo.create("Fall 2027")
    with pytest.raises(ValueError):
        repo.create("fall 2027")  # case-insensitive
    with pytest.raises(ValueError):
        repo.create("   ")


def test_new_opportunities_go_to_the_selected_cycle(conn):
    cycles = CyclesRepo(conn)
    fall = cycles.create("Fall 2026", "2026-09-01", "2026-12-31")
    summer = cycles.create("Summer 2028", "2028-05-01", "2028-08-31")
    opps = OpportunitiesRepo(conn)

    cycles.set_view(fall.id)
    assert opps.create(Opportunity(title="One")).cycle_id == fall.id

    cycles.set_view(summer.id)
    assert opps.create(Opportunity(title="Two")).cycle_id == summer.id


def test_explicit_cycle_is_respected(conn):
    cycles = CyclesRepo(conn)
    fall = cycles.create("Fall 2026")
    cycles.create("Summer 2028")
    cycles.set_view(fall.id)
    other = cycles.get_by_name("Summer 2028")
    assert OpportunitiesRepo(conn).create(Opportunity(title="X", cycle_id=other.id)).cycle_id == other.id


def test_archived_cycle_never_receives_new_records(conn):
    cycles = CyclesRepo(conn)
    old = cycles.create("Fall 2026", "2026-09-01", "2026-12-31")
    new = cycles.create("Fall 2027", "2027-09-01", "2027-12-31")
    cycles.set_view(old.id)
    cycles.archive(old.id)

    # Viewing the archived cycle (to look something up) must not make it the
    # place LinkedIn captures silently land.
    assert cycles.capture_target_id() == new.id


def test_all_cycles_view_captures_into_the_last_cycle_worked_in(conn):
    cycles = CyclesRepo(conn)
    a = cycles.create("Fall 2027", "2027-09-01", "2027-12-31")
    cycles.create("Summer 2028", "2028-05-01", "2028-08-31")  # newer, but not the one being worked in
    cycles.set_view(a.id)
    cycles.set_view(None)

    assert cycles.view_cycle_id() is None
    assert cycles.capture_target_id() == a.id


def test_deleting_a_cycle_requires_it_to_be_empty(conn):
    cycles = CyclesRepo(conn)
    cycle = cycles.create("Fall 2026")
    OpportunitiesRepo(conn).create(Opportunity(title="X", cycle_id=cycle.id))
    with pytest.raises(ValueError):
        cycles.delete(cycle.id)

    empty = cycles.create("Spring 2027")
    cycles.delete(empty.id)
    assert cycles.get(empty.id) is None


def test_deleting_the_selected_cycle_falls_back_to_a_valid_one(conn):
    cycles = CyclesRepo(conn)
    keep = cycles.create("Fall 2026", "2026-09-01", "2026-12-31")
    doomed = cycles.create("Spring 2027", "2027-01-01", "2027-04-30")
    cycles.set_view(doomed.id)
    cycles.delete(doomed.id)
    assert cycles.view_cycle_id() == keep.id


# -- listing / moving ------------------------------------------------------


def test_list_all_filters_by_cycle(conn):
    cycles = CyclesRepo(conn)
    fall = cycles.create("Fall 2026")
    summer = cycles.create("Summer 2028")
    opps = OpportunitiesRepo(conn)
    opps.create(Opportunity(title="Fall job", cycle_id=fall.id))
    opps.create(Opportunity(title="Summer job", cycle_id=summer.id))

    assert [o.title for o in opps.list_all(cycle_id=fall.id)] == ["Fall job"]
    assert [o.title for o in opps.list_all(cycle_id=summer.id)] == ["Summer job"]
    assert len(opps.list_all()) == 2  # no cycle == every cycle (used by Excel export)


def test_move_to_cycle_reassigns_and_logs(conn):
    cycles = CyclesRepo(conn)
    fall = cycles.create("Fall 2026")
    summer = cycles.create("Summer 2028")
    opps = OpportunitiesRepo(conn)
    a = opps.create(Opportunity(title="A", cycle_id=fall.id))
    b = opps.create(Opportunity(title="B", cycle_id=summer.id))  # already there: not counted

    assert opps.move_to_cycle([a.id, b.id], summer.id, summer.name) == 1
    assert opps.get(a.id).cycle_id == summer.id
    assert any("Moved to Summer 2028" in (e.description or "") for e in opps.get_activity(a.id))


# -- dedupe: the same role next cycle is not a duplicate ----------------------


def _scraped(**overrides) -> ScrapedJob:
    defaults = dict(
        linkedin_job_id=None, linkedin_url=None, canonical_linkedin_url=None,
        title="Software Engineer Intern", company_name="Acme Inc.",
    )
    defaults.update(overrides)
    return ScrapedJob(**defaults)


def test_same_role_in_a_new_cycle_is_a_new_record_not_a_duplicate(conn):
    cycles = CyclesRepo(conn)
    old = cycles.create("Fall 2026", "2026-09-01", "2026-12-31")
    new = cycles.create("Fall 2027", "2027-09-01", "2027-12-31")
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    opps.create(Opportunity(title="Software Engineer Intern", company_id=company.id, cycle_id=old.id))

    cycles.set_view(new.id)
    result = match(_scraped(linkedin_job_id="4242"), opps, companies)
    assert result.decision == MatchDecision.NEW_RECORD

    # ...but within the same cycle the existing "flag for review" behavior is unchanged.
    cycles.set_view(old.id)
    cycles.unarchive(old.id)
    result = match(_scraped(linkedin_job_id="4242"), opps, companies)
    assert result.decision == MatchDecision.FLAG_CANDIDATE


def test_exact_linkedin_id_still_matches_across_cycles(conn):
    """The same posting is the same job no matter which cycle it was filed in."""
    cycles = CyclesRepo(conn)
    old = cycles.create("Fall 2026", "2026-09-01", "2026-12-31")
    new = cycles.create("Fall 2027", "2027-09-01", "2027-12-31")
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    existing = opps.create(Opportunity(title="X", company_id=company.id, linkedin_job_id="777", cycle_id=old.id))

    cycles.set_view(new.id)
    result = match(_scraped(linkedin_job_id="777"), opps, companies)
    assert result.decision == MatchDecision.EXACT_MATCH
    assert result.matched_opportunity.id == existing.id


# -- analytics ------------------------------------------------------------


def test_dashboard_analytics_are_scoped_to_a_cycle(conn):
    cycles = CyclesRepo(conn)
    fall = cycles.create("Fall 2026")
    summer = cycles.create("Summer 2028")
    opps = OpportunitiesRepo(conn)
    for _ in range(3):
        opps.create(Opportunity(title="F", status="Rejected", cycle_id=fall.id))
    opps.create(Opportunity(title="S", status="Offer", cycle_id=summer.id))

    fall_outcomes = {s.label: s.count for s in compute_dashboard_analytics(conn, cycle_id=fall.id).outcomes}
    summer_funnel = {s.label: s.count for s in compute_dashboard_analytics(conn, cycle_id=summer.id).funnel}
    assert fall_outcomes["Rejected"] == 3
    assert summer_funnel["Offer"] == 1


def test_summarize_cycle_counts_and_open_applications(conn):
    cycle = CyclesRepo(conn).create("Fall 2026")
    opps = OpportunitiesRepo(conn)
    for status in ("Saved", "Applied", "Applied", "Interview 1", "Offer", "Rejected"):
        opps.create(Opportunity(title=status, status=status, cycle_id=cycle.id))

    s = summarize_cycle(opps.list_all(cycle_id=cycle.id))
    assert (s.total, s.applied, s.interviewed, s.offers, s.rejected) == (6, 5, 2, 1, 1)
    assert s.still_open == 4  # Applied x2, Interview 1, Offer — Rejected is resolved


# -- excel ----------------------------------------------------------------


def test_export_includes_a_cycle_column(conn):
    cycles = CyclesRepo(conn)
    fall = cycles.create("Fall 2026")
    summer = cycles.create("Summer 2028")
    company = CompaniesRepo(conn).get_or_create("Acme Inc.")
    opps = OpportunitiesRepo(conn)
    opps.create(Opportunity(title="A", company_id=company.id, cycle_id=fall.id))
    opps.create(Opportunity(title="B", company_id=company.id, cycle_id=summer.id))

    df = build_all_opportunities(conn)
    assert set(df["Cycle"]) == {"Fall 2026", "Summer 2028"}


def _import_rows(tmp_path, rows):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("All Opportunities")
    ws.append(["Application ID", "Company", "Role", "Cycle", "Status"])
    for row in rows:
        ws.append(row)
    path = tmp_path / "import.xlsx"
    wb.save(path)
    return path


def test_import_assigns_and_creates_named_cycles(conn, tmp_path):
    result = import_workbook(conn, _import_rows(tmp_path, [[None, "Acme Inc.", "Intern", "Summer 2028", "Saved"]]))

    assert result.opportunities_created == 1
    opp = OpportunitiesRepo(conn).list_all()[0]
    assert CyclesRepo(conn).get(opp.cycle_id).name == "Summer 2028"


def test_import_without_a_cycle_uses_the_one_being_worked_in(conn, tmp_path):
    cycles = CyclesRepo(conn)
    working = cycles.create("Fall 2027", "2027-09-01", "2027-12-31")
    cycles.set_view(working.id)

    import_workbook(conn, _import_rows(tmp_path, [[None, "Acme Inc.", "Intern", None, "Saved"]]))

    assert OpportunitiesRepo(conn).list_all()[0].cycle_id == working.id


def test_import_can_move_an_existing_row_between_cycles(conn, tmp_path):
    cycles = CyclesRepo(conn)
    fall = cycles.create("Fall 2026")
    company = CompaniesRepo(conn).get_or_create("Acme Inc.")
    existing = OpportunitiesRepo(conn).create(Opportunity(title="Intern", company_id=company.id, cycle_id=fall.id))

    import_workbook(conn, _import_rows(tmp_path, [[existing.id, "Acme Inc.", "Intern", "Fall 2027", "Saved"]]))

    moved = OpportunitiesRepo(conn).get(existing.id)
    assert CyclesRepo(conn).get(moved.cycle_id).name == "Fall 2027"
