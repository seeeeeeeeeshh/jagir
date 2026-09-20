"""Dataclasses mirroring the SQLite schema (app/db/schema.sql).

These are plain data holders used to pass rows between repositories, the
dedupe engine, and the UI. They intentionally have no behavior beyond
`from_row`/`to_dict` so there is one obvious place (schema.sql) that owns
the real column list.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Optional


def _from_row(cls, row: Any):
    if row is None:
        return None
    names = {f.name for f in fields(cls)}
    return cls(**{k: row[k] for k in row.keys() if k in names})


@dataclass
class Company:
    id: Optional[int] = None
    name: str = ""
    canonical_name: str = ""
    website: Optional[str] = None
    industry: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return _from_row(cls, row)


@dataclass
class Cycle:
    id: Optional[int] = None
    name: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_archived: int = 0
    archived_at: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return _from_row(cls, row)


@dataclass
class Opportunity:
    id: Optional[int] = None

    # identity / classification
    source: str = "manual"
    origin: str = "manual"
    position_type: str = "Internship"
    status: str = "Saved"
    priority: Optional[str] = None
    target_reach_safety: Optional[str] = None
    role_category: Optional[str] = None
    company_id: Optional[int] = None
    cycle_id: Optional[int] = None

    # canonical job-fact fields (LinkedIn-owned once origin is linkedin_import
    # and the record has been claimed by a sync; see dedupe/field_ownership.py)
    title: str = ""
    location: Optional[str] = None
    workplace_type: Optional[str] = None
    employment_type: Optional[str] = None
    salary_text: Optional[str] = None
    job_description: Optional[str] = None
    date_applied: Optional[str] = None
    date_saved: Optional[str] = None
    posting_date: Optional[str] = None
    easy_apply: Optional[int] = None
    external_apply_url: Optional[str] = None
    application_status_shown: Optional[str] = None
    recruiter_name: Optional[str] = None

    # LinkedIn identity/provenance
    linkedin_job_id: Optional[str] = None
    linkedin_url: Optional[str] = None
    canonical_linkedin_url: Optional[str] = None
    linkedin_last_synced_at: Optional[str] = None
    linkedin_metadata_json: Optional[str] = None

    # user-owned
    job_url: Optional[str] = None
    application_deadline: Optional[str] = None
    internship_start_date: Optional[str] = None
    internship_end_date: Optional[str] = None
    offer_date: Optional[str] = None
    rejection_date: Optional[str] = None
    withdrawal_date: Optional[str] = None
    notes: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[str] = None
    resume_version: Optional[str] = None
    cover_letter_version: Optional[str] = None
    portfolio_version: Optional[str] = None
    project_version: Optional[str] = None
    research_notes: Optional[str] = None
    networking_status: Optional[str] = None
    last_contacted_at: Optional[str] = None
    next_follow_up_at: Optional[str] = None

    # dedupe / review
    duplicate_of_id: Optional[int] = None
    needs_review: int = 0
    review_reason: Optional[str] = None
    match_confidence: Optional[float] = None

    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return _from_row(cls, row)


@dataclass
class ApplicationActivity:
    id: Optional[int] = None
    opportunity_id: int = 0
    event_date: str = ""
    event_type: str = ""
    description: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return _from_row(cls, row)


@dataclass
class Contact:
    id: Optional[int] = None
    name: str = ""
    company_id: Optional[int] = None
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    relationship: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return _from_row(cls, row)


@dataclass
class Interview:
    id: Optional[int] = None
    opportunity_id: int = 0
    stage: str = ""
    scheduled_at: Optional[str] = None
    completed_at: Optional[str] = None
    outcome: Optional[str] = None
    prep_notes: Optional[str] = None
    feedback_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return _from_row(cls, row)


@dataclass
class PrepResource:
    id: Optional[int] = None
    title: str = ""
    category: Optional[str] = None
    url_or_path: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return _from_row(cls, row)


@dataclass
class SyncRun:
    id: Optional[int] = None
    started_at: str = ""
    finished_at: Optional[str] = None
    status: str = "running"
    new_saved_count: int = 0
    new_applied_count: int = 0
    updated_count: int = 0
    duplicates_flagged_count: int = 0
    errors_json: Optional[str] = None
    summary_text: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return _from_row(cls, row)


@dataclass
class DuplicateCandidate:
    id: Optional[int] = None
    new_record_payload_json: str = ""
    candidate_opportunity_id: Optional[int] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
    status: str = "pending"
    sync_run_id: Optional[int] = None
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return _from_row(cls, row)
