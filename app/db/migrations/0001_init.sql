-- Jagir database schema.
-- One canonical column per real-world fact (see app/dedupe/field_ownership.py
-- for which fields LinkedIn sync is allowed to overwrite vs which are user-owned).

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    website TEXT,
    industry TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (canonical_name)
);

CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY,

    -- identity / classification
    source TEXT NOT NULL DEFAULT 'manual',
    origin TEXT NOT NULL DEFAULT 'manual',
    position_type TEXT NOT NULL DEFAULT 'Internship',
    status TEXT NOT NULL DEFAULT 'Saved',
    priority TEXT,
    target_reach_safety TEXT,
    role_category TEXT,
    company_id INTEGER REFERENCES companies (id),

    -- canonical job-fact fields
    title TEXT NOT NULL DEFAULT '',
    location TEXT,
    workplace_type TEXT,
    employment_type TEXT,
    salary_text TEXT,
    job_description TEXT,
    date_applied TEXT,
    date_saved TEXT,
    posting_date TEXT,
    easy_apply INTEGER,
    external_apply_url TEXT,
    application_status_shown TEXT,
    recruiter_name TEXT,

    -- LinkedIn identity / provenance (never dual-purpose with the fields above)
    linkedin_job_id TEXT,
    linkedin_url TEXT,
    canonical_linkedin_url TEXT,
    linkedin_last_synced_at TEXT,
    linkedin_metadata_json TEXT,

    -- user-owned fields; LinkedIn sync must never write these
    job_url TEXT,
    application_deadline TEXT,
    internship_start_date TEXT,
    internship_end_date TEXT,
    offer_date TEXT,
    rejection_date TEXT,
    withdrawal_date TEXT,
    notes TEXT,
    next_action TEXT,
    next_action_date TEXT,
    resume_version TEXT,
    cover_letter_version TEXT,
    portfolio_version TEXT,
    project_version TEXT,
    research_notes TEXT,
    networking_status TEXT,
    last_contacted_at TEXT,
    next_follow_up_at TEXT,

    -- dedupe / review
    duplicate_of_id INTEGER REFERENCES opportunities (id),
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_reason TEXT,
    match_confidence REAL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_opp_linkedin_job_id ON opportunities (linkedin_job_id);
CREATE INDEX IF NOT EXISTS idx_opp_canonical_url ON opportunities (canonical_linkedin_url);
CREATE INDEX IF NOT EXISTS idx_opp_company_title ON opportunities (company_id, title);
CREATE INDEX IF NOT EXISTS idx_opp_status ON opportunities (status);
CREATE INDEX IF NOT EXISTS idx_opp_needs_review ON opportunities (needs_review);
CREATE INDEX IF NOT EXISTS idx_opp_position_type ON opportunities (position_type);

CREATE TABLE IF NOT EXISTS application_activity (
    id INTEGER PRIMARY KEY,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities (id),
    event_date TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_opportunity ON application_activity (opportunity_id);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    company_id INTEGER REFERENCES companies (id),
    title TEXT,
    linkedin_url TEXT,
    email TEXT,
    phone TEXT,
    relationship TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunity_contacts (
    opportunity_id INTEGER NOT NULL REFERENCES opportunities (id),
    contact_id INTEGER NOT NULL REFERENCES contacts (id),
    role_in_application TEXT NOT NULL DEFAULT 'networking',
    PRIMARY KEY (opportunity_id, contact_id, role_in_application)
);

CREATE TABLE IF NOT EXISTS interviews (
    id INTEGER PRIMARY KEY,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities (id),
    stage TEXT NOT NULL,
    scheduled_at TEXT,
    completed_at TEXT,
    outcome TEXT,
    prep_notes TEXT,
    feedback_notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_interviews_opportunity ON interviews (opportunity_id);

CREATE TABLE IF NOT EXISTS prep_resources (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT,
    url_or_path TEXT,
    notes TEXT,
    tags TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunity_prep_resources (
    opportunity_id INTEGER NOT NULL REFERENCES opportunities (id),
    prep_resource_id INTEGER NOT NULL REFERENCES prep_resources (id),
    PRIMARY KEY (opportunity_id, prep_resource_id)
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    new_saved_count INTEGER NOT NULL DEFAULT 0,
    new_applied_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    duplicates_flagged_count INTEGER NOT NULL DEFAULT 0,
    errors_json TEXT,
    summary_text TEXT
);

CREATE TABLE IF NOT EXISTS raw_snapshots (
    id INTEGER PRIMARY KEY,
    sync_run_id INTEGER REFERENCES sync_runs (id),
    opportunity_id INTEGER REFERENCES opportunities (id),
    page_type TEXT NOT NULL,
    url TEXT,
    raw_html_or_json TEXT,
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_sync_run ON raw_snapshots (sync_run_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_captured_at ON raw_snapshots (captured_at);

CREATE TABLE IF NOT EXISTS duplicate_candidates (
    id INTEGER PRIMARY KEY,
    new_record_payload_json TEXT NOT NULL,
    candidate_opportunity_id INTEGER REFERENCES opportunities (id),
    confidence REAL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    sync_run_id INTEGER REFERENCES sync_runs (id),
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dupcand_status ON duplicate_candidates (status);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
