# Design

<!-- impeccable:design-schema 1 -->

## Direction

**Dark developer console.** Graphite ground, hairline-seam panels, tabular monospaced figures, status communicated only through a small fixed accent palette. The app reads as one persistent instrument panel the user operates, not a stack of pages they visit. Full contract: `.impeccable/surfaces/app-ui.md`.

## Tokens

Defined in `app/ui/theme.py`, injected globally by `theme.apply_theme()` (called once per page load from `page_frame`).

| Token | Value | Use |
|---|---|---|
| `--jg-bg` | `#15171b` | page background |
| `--jg-panel` | `#1b1e24` | card/panel fill |
| `--jg-panel-raised` | `#20242b` | dialogs, hover state |
| `--jg-border` | `#2a2e37` | hairline seams — never a shadow |
| `--jg-text` / `--jg-text-dim` / `--jg-text-faint` | `#e4e6eb` / `#8b93a1` / `#5b6270` | primary / secondary / quiet text |
| `--jg-blue` | `#5b9dd9` | active/in-progress status, links, primary actions |
| `--jg-amber` | `#e0a83a` | needs-attention / urgent |
| `--jg-green` | `#5fb88a` | offer / positive |
| `--jg-red` | `#d9706b` | destructive actions only — never status decoration |

Typography: system sans for prose; `ui-monospace` stack with `font-variant-numeric: tabular-nums` (`.jg-mono`) for every date, count, and numeric field. Panel headers are small-caps, letter-spaced (`.jg-panel-title`).

## Components

- **Panels** — `ui.card()`, globally restyled: `--jg-panel` fill, 1px `--jg-border`, `border-radius: 6px`, no box-shadow. This is the only card treatment; do not add shadows or alternate card styles.
- **Nav shell** — persistent left drawer (`app/ui/layout.py:page_frame`), collapses behind a header hamburger below the `768px` breakpoint. `active_path` marks the current route with a left accent bar (`.jg-nav-active`).
- **Status badge** — `theme.badge(text, category)`. Category is one of `pending / prepping / active / attention / positive / closed`, mapped from domain values via `theme.status_category()`, `theme.urgency_category()`, `theme.health_category()`. Adding a new status/urgency/health value means adding one line to the relevant `_..._CATEGORY` dict in `theme.py` — never hardcode a color at the call site.
- **Priority chip** — `theme.priority_chip(priority)`. Priority reads as accent weight (High solid → Low faint outline), all in the blue family — not size or a separate color per level.
- **Destructive isolation** — `.jg-destructive` class: outline-only, red, `margin-left: 1.5rem` to separate it from neighboring actions. Apply to any future reject/delete/withdraw button that sits next to a safe action.
- **Readout strip** — `.jg-readout` / `.jg-readout-value` / `.jg-readout-label`: compact tabular counts (Dashboard). Not stat cards — no icons, no big rounded tiles. Wraps via `flex-wrap` with `flex: 1 1 100px` per cell at mobile widths.
- **ag-Grid** — `.ag-theme-balham-dark` with CSS vars pointed at the token set (`opportunity_table.py`). Status/urgency/health columns color via a `:cellStyle` JS function keyed off the same `theme._..._CATEGORY` maps as the badge helper, so the grid and every other status color always agree. **Every column needs an explicit `minWidth`** — ag-Grid's `flex` alone will collapse columns to unreadable slivers when there are many columns in a narrow container (this broke Title/Company during build; see `opportunity_table.py:COLUMN_DEFS`).
- **Forms/dialogs** — Quasar dark mode (`ui.dark_mode().enable()`) handles inputs/selects/date pickers; dialogs get `--jg-panel-raised` (one step lighter than page panels) via `.q-dialog .q-card`. Primary submit buttons use `.props("unelevated")`; Cancel stays `.props("flat")`.

## Patterns

- Color is never decorative — every accent color maps to a real status/urgency/health/priority value through `theme.py`'s category dicts. A new page must reuse these, not invent a new color.
- Tables of domain data get `.jg-mono` on numeric/date columns (and, for dense ledgers like Companies, the whole table) for the console's tabular-figures character.
- Panel titles are always `.jg-panel-title` (small-caps, letter-spaced, dim) — never bold prose headers.
- Empty states and "not built yet" states (Sync page) stay honest: dim text, disabled controls with an outline treatment, no fake data.
- Dashboard leads with the readout strip, then a "Needs attention" panel that surfaces urgent deadlines, stale applications, and duplicate-review flags above the raw counts — per the product principle that this is a daily-use instrument, not a first-impression showpiece.

## Known gaps / next surface

- Star-atlas-style coordinate dashboard was considered and explicitly deferred (see surface brief) — worth revisiting for the Dashboard specifically once Sync/Excel/analytics land, without touching the console system used everywhere else.
- Interviews/Networking/Prep list pages still use plain `ui.table` rather than the ag-Grid treatment; fine for their current row counts, revisit if they grow.
