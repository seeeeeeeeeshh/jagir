"""Applies one matcher decision (app/dedupe/matcher.py) to the database.
Shared by every entry point that produces a ScrapedJob — the Playwright
orchestrator (app/sync/sync_orchestrator.py) and the bookmarklet capture
endpoint (app/sync/bookmarklet_capture.py) — so the merge/flag/create
behavior is identical regardless of how the data was collected.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import asdict

from app.core.models import DuplicateCandidate, Opportunity, SyncRun
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.duplicate_candidates_repo import DuplicateCandidatesRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.dedupe import matcher as matcher_module
from app.dedupe.merge import changed_fields, merge_linkedin_fields
from app.sync.scraped_types import ScrapedJob


def apply_scraped_job(
    scraped: ScrapedJob,
    list_type: str,
    run: SyncRun,
    opp_repo: OpportunitiesRepo,
    company_repo: CompaniesRepo,
    dup_repo: DuplicateCandidatesRepo,
) -> None:
    result = matcher_module.match(scraped, opp_repo, company_repo)

    if result.decision == matcher_module.MatchDecision.EXACT_MATCH:
        existing = opp_repo.get(result.matched_opportunity.id)  # re-fetch fresh, never reuse a stale object
        merged = merge_linkedin_fields(existing, scraped)
        changed = changed_fields(existing, merged)
        opp_repo.update(
            merged,
            log_event=("linkedin_sync", f"Updated from LinkedIn sync: {', '.join(changed) or 'no changes'}"),
        )
        run.updated_count += 1

    elif result.decision == matcher_module.MatchDecision.FLAG_CANDIDATE:
        matched = opp_repo.get(result.matched_opportunity.id)
        # list_type isn't a ScrapedJob field (it's a parameter alongside
        # it), but "keep both" later needs it to set the right status on
        # the new record it creates — stash it in the stored payload so
        # that decision, made after this run ends, still has it.
        payload = asdict(scraped)
        payload["list_type"] = list_type
        dup_repo.create(
            DuplicateCandidate(
                new_record_payload_json=json.dumps(payload),
                candidate_opportunity_id=matched.id,
                confidence=result.confidence,
                reason=result.reason,
                sync_run_id=run.id,
            )
        )
        matched.needs_review = 1
        matched.review_reason = result.reason
        matched.match_confidence = result.confidence
        opp_repo.update(matched)
        run.duplicates_flagged_count += 1

    else:  # NEW_RECORD
        company = company_repo.get_or_create(scraped.company_name)
        opp = opportunity_from_scraped(scraped, company.id, list_type)
        opp_repo.create(opp, event_type="linkedin_sync", description=f"Imported from LinkedIn — {scraped.title}")
        if list_type == "applied":
            run.new_applied_count += 1
        else:
            run.new_saved_count += 1


def opportunity_from_scraped(scraped: ScrapedJob, company_id: int, list_type: str = "saved") -> Opportunity:
    # list_type is the ground truth for which LinkedIn list this came from —
    # it doesn't depend on date_applied being set (the bookmarklet/extension
    # originally never sent one at all, so falling back to "does
    # date_applied exist" always evaluated to "Saved" regardless of
    # list_type; that was the bug). They now send an approximate
    # date_applied too, parsed client-side from LinkedIn's own "Applied 1w
    # ago" text — scraped.date_applied still wins over list_type here if
    # the two ever disagree, since a real date is more specific than which
    # list a card was found on.
    status = "Applied" if (list_type == "applied" or scraped.date_applied) else "Saved"
    return Opportunity(
        source="linkedin",
        origin="linkedin_import",
        status=status,
        company_id=company_id,
        title=scraped.title,
        location=scraped.location,
        workplace_type=scraped.workplace_type,
        employment_type=scraped.employment_type,
        salary_text=scraped.salary_text,
        job_description=scraped.job_description,
        date_applied=scraped.date_applied,
        date_saved=scraped.date_saved,
        posting_date=scraped.posting_date,
        easy_apply=scraped.easy_apply,
        external_apply_url=scraped.external_apply_url,
        application_status_shown=scraped.application_status_shown,
        recruiter_name=scraped.recruiter_name,
        linkedin_job_id=scraped.linkedin_job_id,
        linkedin_url=scraped.linkedin_url,
        canonical_linkedin_url=scraped.canonical_linkedin_url,
        linkedin_last_synced_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        linkedin_metadata_json=json.dumps(scraped.raw_metadata),
    )
