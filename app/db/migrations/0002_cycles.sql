-- Application cycles (e.g. "Fall 2026", "Summer 2028"): every opportunity
-- belongs to exactly one cycle, and a finished cycle can be archived so it
-- drops out of the everyday views without losing any history.

CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (name)
);

-- Tiny key/value store for UI state that must survive a restart and be
-- visible to non-UI code paths (LinkedIn capture endpoints have no browser
-- session to ask which cycle is selected).
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

ALTER TABLE opportunities ADD COLUMN cycle_id INTEGER REFERENCES cycles (id);
CREATE INDEX IF NOT EXISTS idx_opp_cycle ON opportunities (cycle_id);

-- Everything that exists before cycles were introduced was collected in the
-- Sep-Dec 2026 application season. A brand-new database has no rows, so it
-- gets no cycle here; the app creates a default one for today's date on
-- first use.
INSERT INTO cycles (name, start_date, end_date, created_at)
SELECT 'Fall 2026', '2026-09-01', '2026-12-31', datetime('now')
WHERE EXISTS (SELECT 1 FROM opportunities);

UPDATE opportunities
SET cycle_id = (SELECT id FROM cycles WHERE name = 'Fall 2026')
WHERE cycle_id IS NULL AND EXISTS (SELECT 1 FROM cycles WHERE name = 'Fall 2026');

INSERT INTO app_settings (key, value)
SELECT 'current_cycle_id', CAST(id AS TEXT) FROM cycles WHERE name = 'Fall 2026';
