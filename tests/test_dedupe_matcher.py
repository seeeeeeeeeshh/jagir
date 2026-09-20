from app.core.models import Opportunity
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.dedupe.matcher import MatchDecision, match
from app.sync.scraped_types import ScrapedJob


def _scraped(**overrides) -> ScrapedJob:
    defaults = dict(
        linkedin_job_id=None,
        linkedin_url=None,
        canonical_linkedin_url=None,
        title="Software Engineer Intern",
        company_name="Acme Inc.",
    )
    defaults.update(overrides)
    return ScrapedJob(**defaults)


def test_exact_match_by_linkedin_job_id(conn):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    existing = opps.create(Opportunity(title="Totally Different Title", company_id=company.id, linkedin_job_id="123"))

    result = match(_scraped(linkedin_job_id="123", title="Whatever LinkedIn Calls It Now"), opps, companies)

    assert result.decision == MatchDecision.EXACT_MATCH
    assert result.matched_opportunity.id == existing.id


def test_exact_match_by_canonical_url_when_job_id_absent(conn):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    existing = opps.create(
        Opportunity(title="Backend Intern", company_id=company.id, canonical_linkedin_url="https://linkedin.com/jobs/view/999")
    )

    result = match(_scraped(canonical_linkedin_url="https://linkedin.com/jobs/view/999"), opps, companies)

    assert result.decision == MatchDecision.EXACT_MATCH
    assert result.matched_opportunity.id == existing.id


def test_job_id_match_wins_over_url_match_on_different_records(conn):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    by_id = opps.create(Opportunity(title="By Job Id", company_id=company.id, linkedin_job_id="123"))
    opps.create(
        Opportunity(title="By URL", company_id=company.id, canonical_linkedin_url="https://linkedin.com/jobs/view/999")
    )

    result = match(
        _scraped(linkedin_job_id="123", canonical_linkedin_url="https://linkedin.com/jobs/view/999"), opps, companies
    )

    assert result.matched_opportunity.id == by_id.id


def test_fuzzy_flag_same_company_similar_title(conn):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    existing = opps.create(Opportunity(title="Software Engineer Intern", company_id=company.id, origin="manual"))

    # "Acme" (no legal suffix) should canonicalize to the same company as "Acme Inc."
    result = match(_scraped(title="Software Engineering Intern", company_name="Acme"), opps, companies)

    assert result.decision == MatchDecision.FLAG_CANDIDATE
    assert result.matched_opportunity.id == existing.id
    assert result.confidence >= 0.85


def test_fuzzy_no_match_different_title_same_company(conn):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    opps.create(Opportunity(title="Marketing Intern", company_id=company.id))

    result = match(_scraped(title="Data Engineer Intern", company_name="Acme Inc."), opps, companies)

    assert result.decision == MatchDecision.NEW_RECORD


def test_new_record_no_company_overlap(conn):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)

    result = match(_scraped(company_name="Totally New Company"), opps, companies)

    assert result.decision == MatchDecision.NEW_RECORD
    assert result.matched_opportunity is None


def test_candidate_already_claimed_by_different_job_id_excluded_from_fuzzy_pool(conn):
    companies = CompaniesRepo(conn)
    opps = OpportunitiesRepo(conn)
    company = companies.get_or_create("Acme Inc.")
    opps.create(Opportunity(title="Software Engineer Intern", company_id=company.id, linkedin_job_id="999"))

    result = match(_scraped(title="Software Engineer Intern", linkedin_job_id="123"), opps, companies)

    assert result.decision == MatchDecision.NEW_RECORD
