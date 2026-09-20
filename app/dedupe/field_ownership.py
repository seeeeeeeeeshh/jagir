"""Declares which `opportunities` columns LinkedIn sync is allowed to write.

There is exactly one canonical column per real-world fact (e.g. `title`, not
`title` + `li_title`) — this map is what decides who owns it, not the column
name. `dedupe/merge.py` is the only code allowed to write LINKEDIN_OWNED_FIELDS
during a sync; every other write path (manual edits in the UI) touches
USER_OWNED_FIELDS or LINKEDIN_OWNED_FIELDS at the user's own discretion,
since before a record has ever synced, its canonical fields are simply
user-entered.
"""

LINKEDIN_OWNED_FIELDS = {
    "title",
    "location",
    "workplace_type",
    "employment_type",
    "salary_text",
    "job_description",
    "date_applied",
    "date_saved",
    "posting_date",
    "easy_apply",
    "external_apply_url",
    "application_status_shown",
    "recruiter_name",
    "linkedin_job_id",
    "linkedin_url",
    "canonical_linkedin_url",
    "linkedin_last_synced_at",
    "linkedin_metadata_json",
}

USER_OWNED_FIELDS = {
    "notes",
    "next_action",
    "next_action_date",
    "resume_version",
    "cover_letter_version",
    "portfolio_version",
    "project_version",
    "research_notes",
    "networking_status",
    "last_contacted_at",
    "next_follow_up_at",
    "application_deadline",
    "status",
    "priority",
    "target_reach_safety",
    "internship_start_date",
    "internship_end_date",
    "offer_date",
    "rejection_date",
    "withdrawal_date",
    "job_url",
    "cycle_id",
}

DEDUPE_OWNED_FIELDS = {
    "duplicate_of_id",
    "needs_review",
    "review_reason",
    "match_confidence",
}

assert not (LINKEDIN_OWNED_FIELDS & USER_OWNED_FIELDS), "A field cannot be both LinkedIn-owned and user-owned"
assert not (LINKEDIN_OWNED_FIELDS & DEDUPE_OWNED_FIELDS), "A field cannot be both LinkedIn-owned and dedupe-owned"
assert not (USER_OWNED_FIELDS & DEDUPE_OWNED_FIELDS), "A field cannot be both user-owned and dedupe-owned"
