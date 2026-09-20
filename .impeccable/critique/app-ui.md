# Critique: app/ui (dark developer console)

Two independent assessments (separate agents, zero shared context, per
Impeccable's critique methodology — Nielsen's heuristics, cognitive-load
checklist, persona-based walkthroughs) were run against the app after the
initial dark-console design system shipped. Findings below are the merged
result; user confirmed scope as "everything in the report," priority
"Trust & error handling" first. Status reflects this repo as of the fix
pass that followed.

## P0

- **Debug-log language leaking into the user-visible activity timeline**
  (status-change entries read like internal event names, not something a
  person tracking their own job search would write). — **Fixed**: all 111
  existing `application_activity` rows rewritten; new entries use
  plain-language descriptions (`app/ui/pages/application_detail_page.py`).
- **No "Add Opportunity" affordance from the Dashboard** — a first-time or
  returning user landing on `/dashboard` had no path to add a record
  without navigating elsewhere first. — **Fixed**: moved into the
  persistent header (`app/ui/layout.py`), replacing the old per-page button
  on the list pages so there's one consistent entry point everywhere.

## P1

- **Raw exception text shown directly to the user** on Sync failures
  (`sync_orchestrator.py`'s `f"Sync failed: {exc}"`) and Excel import
  failures (`layout.py`'s `_open_import_dialog`) — a Playwright timeout or
  a zipfile error is not something a non-technical user can act on. —
  **Fixed**: `app/core/errors.py::humanize_exception` maps known causes to
  plain language with a next step; unknown causes fall back to the
  exception's first line only (never a full traceback). Wired into both
  call sites and per-record sync errors.
- **Status changes commit instantly with no undo**, including a silent
  side effect (auto-stamping `date_applied` the first time a record leaves
  a pre-application status) — a misclick has a real, hard-to-notice
  consequence. — **Fixed**: inline "Undo" banner appears after a status
  change (`application_detail_page.py`), reverts both the status and any
  auto-stamped date, logs the revert to the timeline distinctly from the
  original change.
- **Dashboard shows confidently-wrong numbers with no staleness signal** —
  pipeline counts are LinkedIn-derived but nothing told the user how
  current that picture was. — **Fixed**: dashboard now shows "As of last
  LinkedIn sync: {timestamp}" (or an explicit "no sync has run yet" state)
  with a direct link to Sync.

## P2 / visual polish (detector-confirmed)

- Undersized text (10-11px labels/badges across every page) — **Fixed**:
  `.jg-panel-title`, `.jg-badge`, `.jg-readout-label`, `.q-table th` bumped
  to a 12px floor (`app/ui/theme.py`).
- Low-contrast `TEXT_FAINT` (#5b6270 on #1b1e24 = 2.7:1, fails WCAG AA) —
  **Fixed**: replaced with #838b99 (4.9:1).
- Zero-value bar-chart rows rendered a colored nub (green/amber/grey
  depending on category) that read as "a small positive value" instead of
  "nothing" — **Fixed**: `theme.bar_row()` renders no fill at all when
  count is 0; the track (and tooltip, if any) stays but the accent color
  is gone.
- Sync page's "failed" run status used the same muted grey as "closed",
  not visually distinct as an error — **Fixed**: added a `negative`
  category (`ACCENT_RED`) to `theme.py`, wired into `sync_page.py`.
- Mixed mono/proportional font treatment in the opportunity detail page's
  "Job info" card, compounded by an unrelated font-size switch on the same
  lines — **Fixed**: unified all metadata lines to `text-sm`, kept `jg-mono`
  reserved for genuinely tabular fields (dates, source/origin codes).
- No tooltip on truncated grid cells (long titles/company names) —
  **Fixed**: `tooltipField` + `enableBrowserTooltips` on the opportunity
  grid (`opportunity_table.py`).
- "By position type" chart at 100% one value conveyed no comparative
  information — **Fixed**: single-category case renders as a stat line
  instead of a full-width bar (`dashboard_page.py`).

## Power-user efficiency

- No bulk status edit (only bulk delete existed) — **Fixed**: "Set status"
  button alongside "Delete selected" on the opportunity list, same
  checkbox-selection UI, respects the same `date_applied` stamping rule as
  the single-record path.
- Search required pressing Enter — **Fixed**: `input-debounce=300` +
  `on_value_change`, filters as you type.
- Add Opportunity dialog was a flat stack of 15 fields — **Fixed**: chunked
  into "What & where" / "Status" / "Dates" sections with hairline dividers.
- Flat nav gave no signal that Applications/Research/Saved Jobs are
  filtered views of the same table as All Opportunities, not separate data
  — **Fixed**: grouped under an "Opportunities" heading, indented.

## Minor observations

- Import/Export Excel buttons appeared on every page including Sync,
  where they're unrelated to that page's flow — **Fixed**: `page_frame`
  takes `show_data_actions`, Sync opts out.
- Native `mm/dd/yyyy` date inputs rendered in light-mode browser chrome
  regardless of app theme — **Fixed**: `color-scheme: dark` on
  `input[type="date"]`.

## Investigated and closed

- Riley-persona observation: "0 flagged for review" across every sync run
  so far despite overlapping companies suggested the dedupe engine might
  not actually be firing on this data. **Investigated, not a bug.** All 111
  real records carry their own `linkedin_job_id`, so every capture takes
  the exact-identity path (`app/dedupe/matcher.py` step 1/2) — either
  auto-merge or a brand-new record. The fuzzy/flag-for-review path (step 3)
  only triggers for a record with *no* identity match, which hasn't
  occurred yet: there are zero manually-entered records in this dataset,
  and the 6 same-company/same-title pairs found in the data are legitimate
  distinct postings (different job IDs) — the matcher correctly excludes
  company-candidates that already have a different claimed
  `linkedin_job_id` from the fuzzy pool, exactly as designed. The
  fuzzy-match branch remains untested against real data, but the reason is
  "hasn't been exercised yet," not "broken."
