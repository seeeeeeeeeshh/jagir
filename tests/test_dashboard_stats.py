from app.analytics.dashboard_stats import (
    compute_company_breakdown,
    compute_dashboard_analytics,
    compute_funnel,
    compute_outcomes,
    compute_position_type_breakdown,
    compute_time_to_response,
)
from app.core.models import Interview, Opportunity
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.interviews_repo import InterviewsRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo


def _stage_counts(stages) -> dict:
    return {s.label: s.count for s in stages}


def test_compute_funnel_buckets_by_current_status(conn):
    opps = OpportunitiesRepo(conn)
    company = CompaniesRepo(conn).get_or_create("Acme")
    for status in ("Saved", "Applied", "Applied", "OA", "Interview 1", "Final Round", "Offer"):
        opps.create(Opportunity(title="x", company_id=company.id, status=status))

    counts = _stage_counts(compute_funnel(opps.list_all()))

    assert counts["Saved"] == 1
    assert counts["Applied"] == 2
    assert counts["Screening"] == 1
    assert counts["Interviewing"] == 1
    assert counts["Final Round"] == 1
    assert counts["Offer"] == 1


def test_compute_outcomes_buckets_terminal_and_hold_statuses(conn):
    opps = OpportunitiesRepo(conn)
    company = CompaniesRepo(conn).get_or_create("Acme")
    for status in ("Accepted", "Rejected", "Rejected", "Withdrawn", "Ghosted", "On Hold"):
        opps.create(Opportunity(title="x", company_id=company.id, status=status))

    counts = _stage_counts(compute_outcomes(opps.list_all()))

    assert counts["Accepted"] == 1
    assert counts["Rejected"] == 2
    assert counts["Withdrawn"] == 1
    assert counts["Ghosted"] == 1
    assert counts["On Hold"] == 1


def test_funnel_and_outcomes_partition_every_status_exactly_once():
    """Every value in STATUS_OPTIONS must land in exactly one funnel or
    outcome bucket — otherwise some opportunities silently vanish from both
    views. This is the regression test for that invariant."""
    from app.core.enums import STATUS_OPTIONS
    from app.analytics.dashboard_stats import _FUNNEL_STAGES, _OUTCOME_STAGES

    covered = set()
    for _, statuses in _FUNNEL_STAGES + _OUTCOME_STAGES:
        assert not (covered & statuses), f"status counted twice: {covered & statuses}"
        covered |= statuses

    assert covered == set(STATUS_OPTIONS), f"uncovered statuses: {set(STATUS_OPTIONS) - covered}"


def test_compute_time_to_response_uses_earliest_interview(conn):
    opps = OpportunitiesRepo(conn)
    interviews = InterviewsRepo(conn)
    company = CompaniesRepo(conn).get_or_create("Acme")

    opp = opps.create(Opportunity(title="x", company_id=company.id, status="Interview 1", date_applied="2026-01-01"))
    interviews.create(Interview(opportunity_id=opp.id, stage="Recruiter Screen", scheduled_at="2026-01-15"))
    interviews.create(Interview(opportunity_id=opp.id, stage="Technical", scheduled_at="2026-01-20"))  # later — ignored

    stats = compute_time_to_response(conn, opps.list_all())

    assert stats.sample_size == 1
    assert stats.median_days == 14
    assert stats.average_days == 14


def test_compute_time_to_response_excludes_opportunities_without_interviews(conn):
    opps = OpportunitiesRepo(conn)
    company = CompaniesRepo(conn).get_or_create("Acme")
    opps.create(Opportunity(title="x", company_id=company.id, status="Applied", date_applied="2026-01-01"))

    stats = compute_time_to_response(conn, opps.list_all())

    assert stats.sample_size == 0
    assert stats.median_days is None


def test_compute_time_to_response_excludes_interview_scheduled_before_applying(conn):
    """A negative delta means bad/inconsistent data (e.g. a manually-logged
    interview date typo) rather than a real signal — excluded rather than
    skewing the average with a nonsensical negative number."""
    opps = OpportunitiesRepo(conn)
    interviews = InterviewsRepo(conn)
    company = CompaniesRepo(conn).get_or_create("Acme")
    opp = opps.create(Opportunity(title="x", company_id=company.id, status="Interview 1", date_applied="2026-01-15"))
    interviews.create(Interview(opportunity_id=opp.id, stage="Recruiter Screen", scheduled_at="2026-01-01"))

    stats = compute_time_to_response(conn, opps.list_all())

    assert stats.sample_size == 0


def test_compute_time_to_response_median_and_average_over_multiple_samples(conn):
    opps = OpportunitiesRepo(conn)
    interviews = InterviewsRepo(conn)
    company = CompaniesRepo(conn).get_or_create("Acme")

    for applied, scheduled in [("2026-01-01", "2026-01-06"), ("2026-01-01", "2026-01-11"), ("2026-01-01", "2026-01-21")]:
        opp = opps.create(Opportunity(title="x", company_id=company.id, status="Interview 1", date_applied=applied))
        interviews.create(Interview(opportunity_id=opp.id, stage="Recruiter Screen", scheduled_at=scheduled))

    stats = compute_time_to_response(conn, opps.list_all())

    assert stats.sample_size == 3
    assert stats.median_days == 10  # deltas: 5, 10, 20
    assert stats.average_days == (5 + 10 + 20) / 3


def test_compute_company_breakdown_counts_and_ranks(conn):
    opps = OpportunitiesRepo(conn)
    companies = CompaniesRepo(conn)
    acme = companies.get_or_create("Acme")
    globex = companies.get_or_create("Globex")

    opps.create(Opportunity(title="a", company_id=acme.id, status="Saved"))
    opps.create(Opportunity(title="b", company_id=acme.id, status="Applied", date_applied="2026-01-01"))
    opps.create(Opportunity(title="c", company_id=acme.id, status="Offer", date_applied="2026-01-01"))
    opps.create(Opportunity(title="d", company_id=globex.id, status="Rejected", date_applied="2026-01-01"))

    breakdown = compute_company_breakdown(conn, opps.list_all())

    acme_stats = next(s for s in breakdown if s.name == "Acme")
    globex_stats = next(s for s in breakdown if s.name == "Globex")
    assert acme_stats.opportunities == 3
    assert acme_stats.applications == 2
    assert acme_stats.offers == 1
    assert globex_stats.rejections == 1
    assert breakdown[0].name == "Acme"  # ranked first — more opportunities


def test_compute_company_breakdown_counts_applications_by_status_not_date_applied(conn):
    """Regression test: LinkedIn list-page captures (the extension,
    bookmarklet, and most sync runs) never populate date_applied — only a
    detail-page fetch does, and that's budget-limited. Counting
    "applications" by date_applied being set previously meant this stayed
    0 for every company regardless of how many were genuinely applied to."""
    opps = OpportunitiesRepo(conn)
    companies = CompaniesRepo(conn)
    acme = companies.get_or_create("Acme")

    opps.create(Opportunity(title="a", company_id=acme.id, status="Saved", date_applied=None))
    opps.create(Opportunity(title="b", company_id=acme.id, status="Applied", date_applied=None))
    opps.create(Opportunity(title="c", company_id=acme.id, status="Interview 1", date_applied=None))

    breakdown = compute_company_breakdown(conn, opps.list_all())

    acme_stats = next(s for s in breakdown if s.name == "Acme")
    assert acme_stats.applications == 2  # "b" and "c" — Saved doesn't count


def test_compute_company_breakdown_respects_limit(conn):
    opps = OpportunitiesRepo(conn)
    companies = CompaniesRepo(conn)
    for i in range(5):
        company = companies.get_or_create(f"Company {i}")
        opps.create(Opportunity(title="x", company_id=company.id, status="Saved"))

    breakdown = compute_company_breakdown(conn, opps.list_all(), limit=2)

    assert len(breakdown) == 2


def test_compute_position_type_breakdown(conn):
    opps = OpportunitiesRepo(conn)
    company = CompaniesRepo(conn).get_or_create("Acme")
    opps.create(Opportunity(title="a", company_id=company.id, position_type="Internship", status="Offer"))
    opps.create(Opportunity(title="b", company_id=company.id, position_type="Internship", status="Saved"))
    opps.create(Opportunity(title="c", company_id=company.id, position_type="Research", status="Saved"))

    breakdown = compute_position_type_breakdown(opps.list_all())

    intern = next(s for s in breakdown if s.position_type == "Internship")
    assert intern.count == 2
    assert intern.offers == 1
    assert breakdown[0].position_type == "Internship"  # ranked first


def test_compute_dashboard_analytics_on_empty_db_does_not_error(conn):
    analytics = compute_dashboard_analytics(conn)

    assert all(s.count == 0 for s in analytics.funnel)
    assert all(s.count == 0 for s in analytics.outcomes)
    assert analytics.time_to_response.sample_size == 0
    assert analytics.by_company == []
    assert analytics.by_position_type == []
