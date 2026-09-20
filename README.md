# Jagir

A local-first job & opportunity tracker: applications, saved jobs, research/RA
positions, networking, interviews, and prep resources, all in one SQLite
database, with LinkedIn capture (a Chrome extension/bookmarklet reading your
own logged-in browser tab, or Playwright automation as an advanced option)
and Excel import/export on top of it.

See `plan.md`-equivalent design notes in the project history for the full
architecture. Short version: SQLite is the single source of truth; Excel/CSV
are import/export formats only; every opportunity record splits into
LinkedIn-owned fields (which sync may overwrite) and user-owned fields
(status, priority, notes, networking, prep — sync must never touch these).
See `app/dedupe/field_ownership.py`.

## Current status

This is being built in phases (see project history for the full build order).
**Implemented so far:**

- SQLite schema + migration runner (`app/db/`)
- Manual CRUD for opportunities, contacts, interviews, prep resources
- NiceGUI UI: Dashboard, All Opportunities, Applications, Research, Saved
  Jobs, Networking, Interviews, Prep, Companies pages, and an opportunity
  detail view with editable pipeline fields and an activity timeline
- Dashboard analytics (`app/analytics/dashboard_stats.py`) — current-stage
  pipeline distribution, outcomes (accepted/rejected/withdrawn/ghosted/on
  hold), time-to-first-interview (median/average, from the interviews
  table's own dates, not activity-log text-mining), and top-companies /
  by-position-type breakdowns. The "funnel" is a current-status snapshot,
  not true historical funnel — the schema doesn't track status-change
  history, so a since-rejected application's peak stage isn't knowable;
  this is called out in the UI itself, not just here.
- Application cycles (`app/db/repositories/cycles_repo.py`, `/cycles` page)
  — every opportunity belongs to a cycle ("Fall 2026", "Summer 2028", ...).
  The sidebar Cycle picker scopes every list and the Dashboard to one cycle
  (or "All cycles"), and new opportunities (Add dialog, LinkedIn capture,
  Excel import) land in the cycle you're working in. A finished cycle can be
  archived: it drops out of everyday views but keeps its history and stays
  reachable from the picker. "Move to cycle" (bulk, in the list) and the
  Cycle field on the detail page carry a role into a new season. Fuzzy
  duplicate detection is scoped to one cycle, so re-applying to the same
  role next year isn't flagged as a duplicate; exact LinkedIn id/URL matches
  stay global. Interviews, Calendar, Companies, Networking and Prep are
  deliberately cross-cycle. Excel export has a Cycle column and import
  honors it (a new name creates the cycle). Existing data was migrated into
  "Fall 2026" by `0002_cycles.sql`. `schema.sql` (used by tests) is kept
  identical in shape to the migrations by `tests/test_cycles.py`.
- Calendar (`/calendar`, Google Calendar): month view by default with a
  Week toggle; click any day to quick-add (Enter to save; a time in the
  title such as "Recruiter call 3pm" makes it a timed event, otherwise
  all-day); "+N more" opens a day's full list; "More options" / "+ Add
  event" open the full dialog with description.
- Derived fields computed at query time: days since application, deadline
  urgency, application health (`app/analytics/derived_fields.py`)
- Excel export + import (`app/excel/`) — export produces one workbook with
  a sheet per view, a Dashboard sheet with a status chart, dropdown-validated
  enum columns, and cell coloring on Status/Urgency/Application Health that
  reuses the same category colors as the app's own badges
  (`app/excel/conditional_format.py`), so the color language matches between
  the app and the sheet. Date columns (Date Applied, Deadline, etc.) are
  written as real Excel dates, not text, so they sort/filter properly;
  "Days Since Application" is a live formula off Date Applied instead of a
  value frozen at export time, so it stays current without a re-export. The
  old "Had OA / Technical / Behavioral / Final Round" Yes/No columns were
  dropped as redundant with "Latest Interview Stage" plus the full
  per-interview history already on the Interviews sheet.
  Import (`app/excel/importer.py`, upload via "Import from Excel" in the
  header) reads edits back from "All Opportunities", Companies, Networking,
  Prep Resources, and Interviews — matched by each sheet's id column (blank
  id = new row); LinkedIn-owned fields (`app/dedupe/field_ownership.py`) on
  an *existing* opportunity row are never overwritten by an import, same
  protection LinkedIn sync gets. A blank cell clears the field it maps to
  (an export is a complete snapshot, not a partial one).
  Applications/Research/Saved Jobs sheets are just filtered views and
  aren't imported — edit opportunities in "All Opportunities" for changes
  to be picked up; reported as skipped, not silently ignored.
- Dedupe/merge engine (`app/dedupe/matcher.py`, `merge.py`) — matches a
  scraped LinkedIn record by exact identity (job id/URL) or flags a fuzzy
  company+title match for manual review; only exact identity matches
  auto-merge, and only `LINKEDIN_OWNED_FIELDS` (`app/dedupe/field_ownership.py`)
  are ever overwritten
- LinkedIn capture, three ways, all routed through the same dedupe engine
  (Sync page):
  - **Chrome extension (recommended)** — `extension/` (Manifest V3, no
    background service worker — all logic lives in the popup). One-time
    "Load unpacked" in `chrome://extensions`. While viewing your Saved Jobs
    or Applied Jobs list, click the toolbar icon and press "Capture from
    this page" in the popup; it reads what's rendered on the page in your
    own already-logged-in tab and posts it to a local endpoint
    (`app/api/linkedin_capture.py` → `app/sync/bookmarklet_capture.py`). No
    cookies, credentials, or browser automation involved — the extension
    only ever touches the page you're already looking at, and only when you
    click the button. The popup shows the captured titles/companies (or the
    specific error) and remembers the last result between opens. LinkedIn's
    saved/applied list is numbered pagination (a "1 2 3 Next" control), not
    infinite scroll — confirmed against a real account. All three capture
    paths click through every page via the Next button's `data-testid`
    (paced with jitter, not machine-speed) until it disappears, merging
    results by URL — so a capture gets your whole list, not just the first
    page's ~10 cards. Verified against a simulated multi-page flow; not yet
    against a real 100+-job list.
  - **Bookmarklet** — same idea (`app/sync/bookmarklet_js.py`), as a plain
    `javascript:` bookmark instead of an installed extension, for anyone who
    doesn't want to load an extension. A bit more manual (drag to bookmarks
    bar each setup), otherwise identical capture behavior.
  - **Automated browser sync** (`app/sync/sync_orchestrator.py`, under
    "Advanced" on the Sync page) — drives a separate, persistent-profile
    Playwright browser through your own LinkedIn session instead. More
    complete (also visits job detail pages on its own), but needs a headed
    browser window for the login step, which only works if the app is run
    from your own interactive terminal (not through a remote/automated
    session).
  - All three paths share `app/dedupe/matcher.py` + `merge.py` (and
    `app/dedupe/apply.py`, which applies one matcher decision — shared by
    every entry point so behavior is identical regardless of how the data
    was collected): exact identity matches (job id/URL) auto-merge, fuzzy
    company+title matches are flagged for manual review, and only
    `LINKEDIN_OWNED_FIELDS` (`app/dedupe/field_ownership.py`) are ever
    overwritten.
  - **List-page selectors (title/company/location — all three paths) are
    verified against real captured LinkedIn markup**
    (`tests/fixtures/html/saved_job_card.html`, from an actual account) —
    they deliberately avoid matching on any CSS class name, since LinkedIn
    generates random hashed class names per deploy, and instead find every
    `/jobs/view/` link and keep the ones wrapping 2+ `<p>` tags. **Job-detail-
    page selectors** (`app/sync/linkedin_scraper.py`'s `_parse_detail_page`,
    used only by the automated-browser path) remain an unverified
    best-effort guess. If a capture ever comes back empty again, LinkedIn
    changed the structure once more — inspect the real page and adjust; the
    extension/bookmarklet selectors are edited directly in JS, no Python
    needed. Matching, merging, and orchestration (everything past "here's a
    list of scraped jobs") are fully unit-tested
    and selector-independent.

- Trust & error handling: raw exceptions from Sync/Excel import are mapped
  to plain-language messages with a next step (`app/core/errors.py`), status
  changes on an opportunity show an inline "Undo" for a few seconds
  (reverting the auto-stamped `date_applied` too if that was the side
  effect being undone), and the Dashboard shows "As of last LinkedIn sync"
  so stale-looking numbers are never silently presented as current.
- Bulk status edit on the opportunity list (select rows via checkbox, same
  UI as bulk delete), live/incremental search (filters as you type, no
  Enter needed).
- Google Calendar (`app/integrations/google_calendar.py`, Calendar page) —
  one-way only: an explicit "Add to Calendar" button on interviews,
  application deadlines, and next-action dates pushes that one item as an
  event; nothing syncs automatically, and Jagir never edits or deletes an
  event it didn't create. The Calendar page shows a real 7-day grid (today
  highlighted) of your own upcoming Google Calendar events for reference
  (read-only), not just a flat list. Requires a one-time Google OAuth
  client of your own — the Calendar page shows exact setup steps if
  `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` aren't set in `.env`. The
  refresh token lives in `data/google_token.json`, deliberately kept out
  of the sqlite db (see Backups below).

Use "+ Add Opportunity" in the header (present on every page) to track
things by hand — those records behave identically to LinkedIn-imported
ones. `python scripts/backup_db.py` backs up the database (via sqlite's
own safe backup API, not a raw file copy) plus a full Excel export,
timestamped into `data/backups/`.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env
python scripts\init_db.py
python -m app.main
```

Then open http://localhost:8080.

## Backups

The whole app is one SQLite file: `data/job_tracker.db`. To back it up, run
`python scripts/backup_db.py` — it uses sqlite's own online backup API
(safe even while Jagir is running/mid-write, unlike a raw file copy) and
also writes a full Excel export, both timestamped into `data/backups/`.

If you've connected Google Calendar, `data/google_token.json` holds a live
refresh token for your Google account — it's deliberately a separate file
from the database specifically so that copying/sharing `job_tracker.db`
(for a backup, or to hand off data) never carries a working credential
along with it. Don't share that file; revoke access any time from the
Calendar page's "Disconnect" button, or from
myaccount.google.com/permissions.

## Project layout

See `app/` — `db/` (schema + repositories), `core/` (enums/models shared
across UI, sync, and dedupe code, plus `core/errors.py` for turning
exceptions into user-facing messages), `ui/` (NiceGUI pages/components,
design system in `ui/theme.py`), `analytics/` (derived fields + dashboard
stats), `sync/` (LinkedIn capture, all three paths), `dedupe/` (matcher +
merge engine), `excel/` (import/export).

Design direction and critique history live under `.impeccable/` — the
"dark developer console" direction contract
(`.impeccable/surfaces/app-ui.md`) and the merged findings from the two-
assessment critique pass, with resolution status per item
(`.impeccable/critique/app-ui.md`).
