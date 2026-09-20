"""Decides what to do with one scraped LinkedIn job record: merge it into an
existing opportunity, flag it for the user to review, or create a new one.

Matching is deliberately conservative: only an exact LinkedIn identity match
(job id or canonical URL) auto-merges. Anything else — even a very high
fuzzy-text score — becomes a review candidate rather than an automatic
merge, because a wrong auto-merge silently overwrites one job's data with
another's and the user may never notice (see app/dedupe/merge.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rapidfuzz import fuzz

from app.core.models import Opportunity
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.cycles_repo import CyclesRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.sync.scraped_types import ScrapedJob

# Token-sort ratio (word-order-tolerant, but still needs most words to match)
# on titles within the same company. Chosen over token_set_ratio, which is
# too permissive on short titles — it would score "Backend Intern" and
# "Backend Intern - ML Team" as near-identical even though those are
# plausibly two distinct postings. 85 flags legitimate title variation
# ("2026 Summer Software Engineer Intern" vs "Software Engineer Intern,
# 2026") while staying above where genuinely different roles at the same
# company ("Data Engineer Intern" vs "Data Scientist Intern") start to
# score from shared common words. Tune here if real data disagrees.
FUZZY_MATCH_THRESHOLD = 85


class MatchDecision(str, Enum):
    EXACT_MATCH = "exact_match"
    FLAG_CANDIDATE = "flag_candidate"
    NEW_RECORD = "new_record"


@dataclass
class MatchResult:
    decision: MatchDecision
    matched_opportunity: Opportunity | None = None
    confidence: float | None = None
    reason: str | None = None


def match(scraped: ScrapedJob, opp_repo: OpportunitiesRepo, company_repo: CompaniesRepo) -> MatchResult:
    if scraped.linkedin_job_id:
        existing = opp_repo.find_by_linkedin_job_id(scraped.linkedin_job_id)
        if existing:
            return MatchResult(MatchDecision.EXACT_MATCH, existing, 1.0, "Matched by LinkedIn job id")

    if scraped.canonical_linkedin_url:
        existing = opp_repo.find_by_canonical_url(scraped.canonical_linkedin_url)
        if existing:
            return MatchResult(MatchDecision.EXACT_MATCH, existing, 1.0, "Matched by canonical LinkedIn URL")

    company = company_repo.get_or_create(scraped.company_name)
    # Fuzzy title/company matching stays inside the cycle a new record would
    # land in: the same role posted again for next year's cycle is a fresh
    # application, not a duplicate of last year's. (The exact LinkedIn id/URL
    # matches above stay global — that is genuinely the same posting.)
    target_cycle_id = CyclesRepo(opp_repo.conn).capture_target_id()
    candidates = [
        c
        for c in opp_repo.find_candidates_by_company(company.id, cycle_id=target_cycle_id)
        # A candidate already claimed by a *different* LinkedIn posting can't
        # also be this one.
        if not (c.linkedin_job_id and c.linkedin_job_id != scraped.linkedin_job_id)
    ]

    best: tuple[Opportunity, float] | None = None
    for candidate in candidates:
        score = fuzz.token_sort_ratio(scraped.title.lower(), candidate.title.lower())
        if score >= FUZZY_MATCH_THRESHOLD and (best is None or score > best[1]):
            best = (candidate, score)

    if best:
        candidate, score = best
        return MatchResult(
            MatchDecision.FLAG_CANDIDATE,
            candidate,
            score / 100,
            f"Title/company similarity {score:.0f}% with an existing record — please confirm this is the same job",
        )

    return MatchResult(MatchDecision.NEW_RECORD)
