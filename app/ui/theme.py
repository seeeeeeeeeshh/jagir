"""Design system for the "dark developer console" direction (see
.impeccable/surfaces/app-ui.md for the full direction contract).

Graphite ground, hairline-seam panels, status/urgency communicated through
a small fixed accent palette — never decoration. `apply_theme()` is called
once per page load from `page_frame`; the badge/chip helpers below are the
only places that know which status maps to which accent, so new statuses
get a color by adding one line here rather than scattering
`if status == ...` through pages.

Two revisions on top of that direction (frontend-design skill pass): a
display face (Space Grotesk) for the wordmark/titles/hero numbers instead
of leaning on system-ui for everything, and ACCENT_BRAND — a color
reserved for Jagir's own identity (wordmark, section markers, "today")
that isn't also a status color, so ACCENT_BLUE goes back to meaning only
"active" and doesn't have to do double duty as "the app's color" too.
Monospace is intentionally scoped down to genuinely tabular figures (grid
date columns, counts, timestamps) rather than applied to buttons/nav/
titles by reflex — see jg-mono's callers for what still legitimately needs
it.
"""

from __future__ import annotations

from nicegui import ui

# -- tokens -------------------------------------------------------------

BG = "#15171b"
PANEL = "#1b1e24"
PANEL_RAISED = "#20242b"
BORDER = "#2a2e37"
TEXT = "#e4e6eb"
TEXT_DIM = "#8b93a1"
TEXT_FAINT = "#838b99"  # 4.9:1 on PANEL — WCAG AA (was #5b6270 at 2.7:1, a design-critique fail)

ACCENT_BLUE = "#5b9dd9"        # active-mid: Recruiter Screen / Interview 1
ACCENT_BLUE_LIGHT = "#7db3e0"  # active-early: Applied / OA — a step lighter, reads as "just started"
ACCENT_BLUE_DEEP = "#5590cc"   # active-late: Interview 2 / Final Round — a step deeper, reads as "further along"
ACCENT_AMBER = "#e0a83a"       # needs attention / urgent
ACCENT_GREEN = "#5fb88a"       # offer / positive
ACCENT_GREEN_DEEP = "#3a9c68"  # accepted — richer than Offer's green; distinctly "further along" the same way
ACCENT_ROSE = "#c8757f"        # rejected — a status outcome, deliberately muted; NOT the same red as ACCENT_RED
ACCENT_RED = "#d9706b"         # destructive only (Delete buttons, sync failures) — never a status outcome color
ACCENT_GREY = "#6b7280"        # pending / closed / quiet
ACCENT_BRAND = "#a78bd6"       # Jagir's own identity — wordmark, section markers, "today" — never a status meaning

DISPLAY_FONT = "'Space Grotesk', ui-sans-serif, system-ui, sans-serif"

# The blue and green families each step through three shades so status
# progression reads visually, not just as a label change: further along
# the pipeline = a deeper shade of the same hue, not an unrelated color.
_CATEGORY_COLOR = {
    "pending": TEXT_FAINT,
    "prepping": ACCENT_BLUE,
    "active-early": ACCENT_BLUE_LIGHT,
    "active-mid": ACCENT_BLUE,
    "active-late": ACCENT_BLUE_DEEP,
    "active": ACCENT_BLUE,  # back-compat alias for any caller not using the finer active-* stages
    "attention": ACCENT_AMBER,
    "positive": ACCENT_GREEN,
    "positive-strong": ACCENT_GREEN_DEEP,
    "declined": ACCENT_ROSE,
    "closed": TEXT_FAINT,
    "negative": ACCENT_RED,  # technical/system failures (Sync page) — distinct from "declined" (a normal outcome)
}

_STATUS_CATEGORY = {
    "Saved": "pending",
    "Interested": "pending",
    "Preparing": "prepping",
    "Applied": "active-early",
    "OA": "active-early",
    "Recruiter Screen": "active-mid",
    "Interview 1": "active-mid",
    "Interview 2": "active-late",
    "Final Round": "active-late",
    "On Hold": "attention",
    "Offer": "positive",
    "Accepted": "positive-strong",
    "Rejected": "declined",
    "Withdrawn": "closed",
    "Ghosted": "closed",
}

_URGENCY_CATEGORY = {
    "Critical": "attention",
    "Soon": "attention",
    "Normal": "pending",
    "No deadline": "closed",
}

_HEALTH_CATEGORY = {
    "Needs action": "attention",
    "Stale": "attention",
    "Active": "pending",
}


def status_category(status: str) -> str:
    return _STATUS_CATEGORY.get(status, "pending")


def urgency_category(urgency: str) -> str:
    return _URGENCY_CATEGORY.get(urgency, "pending")


def health_category(health: str) -> str:
    return _HEALTH_CATEGORY.get(health, "pending")


def category_color(category: str) -> str:
    return _CATEGORY_COLOR.get(category, TEXT_DIM)


def badge(text: str, category: str):
    """A small pill for a status/urgency/health value, colored by category."""
    color = category_color(category)
    el = ui.label(text).classes("jg-badge")
    el.style(f"color:{color}; border-color:{color}40; background:{color}1a;")
    return el


def priority_chip(priority: str | None):
    """Priority as accent weight, not size: High is solid, Medium is muted,
    Low is a faint outline — same blue family throughout, per the direction
    contract (dot-size gimmicks belong to the direction we didn't build)."""
    if not priority:
        return ui.label("—").classes("text-[color:var(--jg-text-faint)]")
    weight = {"High": 1, "Medium": 0.55, "Low": 0.3}.get(priority, 0.3)
    el = ui.label(priority).classes("jg-badge")
    el.style(f"color:{ACCENT_BLUE}; border-color:{ACCENT_BLUE}{int(weight*102):02x}; background:{ACCENT_BLUE}{int(weight*38):02x};")
    return el


def bar_row(label: str, count: int, max_count: int, color: str = ACCENT_BLUE, detail: str | None = None):
    """One row of a magnitude bar chart (funnel stages, company/position
    rankings): fixed-width label, a single-hue proportional bar, count in
    tabular figures. One hue for a magnitude comparison — no categorical
    color-identity problem here, so no palette to validate. `detail` adds a
    native-tooltip aside (e.g. "3 of 12, 25%") without a custom JS layer."""
    # A zero-count row renders no fill at all rather than a colored nub —
    # a min-width nub in the category's accent color (green/amber/grey
    # depending on caller) previously made "zero" look like a small
    # positive value instead of nothing.
    pct = 0 if count <= 0 or max_count <= 0 else max(4, round(count / max_count * 100))
    with ui.row().classes("w-full items-center gap-3 jg-bar-row"):
        ui.label(label).classes("jg-bar-label")
        with ui.element("div").classes("jg-bar-track") as track:
            if pct > 0:
                ui.element("div").classes("jg-bar-fill").style(f"width:{pct}%; background:{color};")
            if detail:
                track.tooltip(detail)
        ui.label(str(count)).classes("jg-mono jg-bar-count")


_CSS = f"""
:root {{
    --jg-bg: {BG};
    --jg-panel: {PANEL};
    --jg-panel-raised: {PANEL_RAISED};
    --jg-border: {BORDER};
    --jg-text: {TEXT};
    --jg-text-dim: {TEXT_DIM};
    --jg-text-faint: {TEXT_FAINT};
    --jg-blue: {ACCENT_BLUE};
    --jg-amber: {ACCENT_AMBER};
    --jg-green: {ACCENT_GREEN};
    --jg-red: {ACCENT_RED};
    --jg-brand: {ACCENT_BRAND};
    --jg-display-font: {DISPLAY_FONT};
}}

body {{
    background: var(--jg-bg) !important;
    color: var(--jg-text);
}}

.jg-mono {{
    font-family: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
}}

/* Numeric columns of an otherwise-plain table (e.g. Companies) — every
   column but the first (a name/label) gets tabular figures; the label
   column stays in normal type instead of the whole table going mono. */
.jg-mono-cols td:not(:first-child) {{
    font-family: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
}}

.jg-display {{
    font-family: var(--jg-display-font);
}}

/* native date inputs (deadline, next action date, etc.) otherwise render
   their mm/dd/yyyy placeholder and calendar icon in light-mode chrome
   regardless of the page theme — this tells the browser to draw its own
   control in dark mode instead. */
input[type="date"] {{
    color-scheme: dark;
}}

.jg-panel-title {{
    font-family: var(--jg-display-font);
    font-size: .92rem;
    font-weight: 500;
    letter-spacing: .01em;
    color: var(--jg-text);
}}
.jg-panel-title::before {{
    content: "";
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: .5rem;
    background: var(--jg-brand);
    border-radius: 1px;
    vertical-align: middle;
}}

.jg-badge {{
    display: inline-flex;
    align-items: center;
    padding: .1rem .55rem;
    border-radius: 3px;
    font-size: .75rem;
    font-weight: 600;
    letter-spacing: .02em;
    border: 1px solid;
    line-height: 1.5;
    white-space: nowrap;
}}

/* -- panels: hairline seams, one step of elevation, never a shadow ---- */
.q-card {{
    background: var(--jg-panel) !important;
    border: 1px solid var(--jg-border) !important;
    border-radius: 6px !important;
    box-shadow: none !important;
}}

.q-header {{
    background: var(--jg-panel) !important;
    border-bottom: 1px solid var(--jg-border);
    box-shadow: none !important;
}}

.q-drawer {{
    background: var(--jg-panel) !important;
    border-right: 1px solid var(--jg-border) !important;
}}

.q-dialog .q-card {{
    background: var(--jg-panel-raised) !important;
}}

/* -- nav ---------------------------------------------------------------- */
.jg-nav-link {{
    display: block;
    padding: .5rem .9rem;
    border-radius: 4px;
    color: var(--jg-text-dim) !important;
    text-decoration: none !important;
    font-size: .84rem;
    letter-spacing: .01em;
    border-left: 2px solid transparent;
}}
.jg-nav-link:hover {{
    color: var(--jg-text) !important;
    background: var(--jg-panel-raised);
}}
.jg-nav-link.jg-nav-active {{
    color: var(--jg-text) !important;
    border-left-color: var(--jg-brand);
    background: var(--jg-panel-raised);
}}
.jg-nav-link.jg-nav-indent {{
    padding-left: 1.75rem;
    font-size: .8rem;
}}
.jg-nav-group-label {{
    display: block;
    padding: .8rem .9rem .15rem;
    font-family: var(--jg-display-font);
    font-size: .72rem;
    letter-spacing: .01em;
    color: var(--jg-text-faint);
}}

/* -- archived-cycle notice: sits above page content, amber = "heads up" - */
.jg-archived-banner {{
    padding: .55rem .9rem;
    border: 1px solid var(--jg-amber);
    border-left-width: 3px;
    border-radius: 4px;
    background: var(--jg-panel);
    color: var(--jg-amber);
}}

/* -- destructive isolation: outline-only, never adjacent by default ---- */
.jg-destructive {{
    color: var(--jg-red) !important;
    border: 1px solid var(--jg-red) !important;
    background: transparent !important;
    margin-left: 1.5rem !important;
}}

/* -- tables / grids: hairline rows, no zebra shadow --------------------- */
.q-table {{
    background: var(--jg-panel) !important;
}}
.q-table th {{
    color: var(--jg-text-dim) !important;
    text-transform: uppercase;
    font-size: .72rem;
    letter-spacing: .06em;
    font-weight: 700;
    border-bottom: 1px solid var(--jg-border) !important;
}}
.q-table td {{
    border-bottom: 1px solid var(--jg-border) !important;
    color: var(--jg-text);
}}
.q-table tbody tr:hover {{
    background: var(--jg-panel-raised) !important;
}}

.ag-theme-balham-dark {{
    --ag-background-color: {PANEL};
    --ag-header-background-color: {PANEL};
    --ag-odd-row-background-color: {PANEL};
    --ag-header-foreground-color: {TEXT_DIM};
    --ag-foreground-color: {TEXT};
    --ag-border-color: {BORDER};
    --ag-row-hover-color: {PANEL_RAISED};
    --ag-font-family: ui-sans-serif, system-ui, sans-serif;
    --ag-font-size: 13px;
}}

/* -- readout strip: compact tabular counts, not stat cards -------------- */
.jg-readout {{
    display: flex;
    flex-direction: column;
    gap: .15rem;
    padding: .6rem 1rem;
    border-right: 1px solid var(--jg-border);
}}
.jg-readout:last-child {{ border-right: none; }}
.jg-readout-value {{
    font-family: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--jg-text);
}}
.jg-readout-label {{
    font-family: var(--jg-display-font);
    font-size: .74rem;
    letter-spacing: .01em;
    color: var(--jg-text-dim);
}}

/* -- magnitude bar chart: single hue, thin, rounded data-ends ----------- */
.jg-bar-row {{ padding: .2rem 0; }}
.jg-bar-label {{
    flex: 0 0 128px;
    font-size: .78rem;
    color: var(--jg-text-dim);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.jg-bar-track {{
    flex: 1 1 auto;
    height: 10px;
    background: var(--jg-panel-raised);
    border-radius: 5px;
    overflow: hidden;
}}
.jg-bar-fill {{
    height: 100%;
    border-radius: 5px;
    min-width: 4px;
    transition: width .2s ease;
}}
.jg-bar-count {{
    flex: 0 0 34px;
    text-align: right;
    font-size: .78rem;
    color: var(--jg-text);
}}

/* -- calendar day cells: click empty space to quick-add an event -------- */
.jg-cal-cell {{
    transition: background .1s ease;
}}
.jg-cal-cell:hover {{
    background: var(--jg-panel-raised);
}}
/* the "+" that appears on hover is the only affordance a click-to-add cell needs */
.jg-cal-plus {{
    opacity: 0;
    margin-left: auto;
    font-size: .95rem;
    line-height: 1;
    color: var(--jg-text-faint);
    transition: opacity .1s ease;
}}
.jg-cal-cell:hover .jg-cal-plus {{
    opacity: 1;
}}
.jg-cal-daynum {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 1.55rem;
    height: 1.55rem;
    padding: 0 .3rem;
    border-radius: 999px;
    font-family: var(--jg-display-font);
    font-size: .78rem;
    font-weight: 600;
}}
.jg-cal-daynum-today {{
    background: var(--jg-brand);
    color: var(--jg-bg);
}}
/* one-line event chip: time (if any) + title, ellipsized instead of hard-cut */
.jg-cal-chip {{
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
    gap: .35rem;
    width: 100%;
    min-width: 0;
    padding: 1px .4rem;
    border-left: 2px solid var(--jg-brand);
    border-radius: 2px;
    background: var(--jg-panel-raised);
    cursor: pointer;
}}
.jg-cal-chip:hover {{
    filter: brightness(1.3);
}}
.jg-cal-chip-time {{
    flex: 0 0 auto;
    font-family: ui-monospace, monospace;
    font-size: .66rem;
    color: var(--jg-text-dim);
}}
.jg-cal-chip-text {{
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    font-size: .74rem;
    color: var(--jg-text);
}}
.jg-cal-chip-dim {{
    opacity: .5;
}}
.jg-cal-more {{
    font-size: .7rem;
    color: var(--jg-text-dim);
    cursor: pointer;
}}
.jg-cal-more:hover {{
    color: var(--jg-text);
    text-decoration: underline;
}}
"""


_FONT_LINKS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
"""


def apply_theme():
    ui.dark_mode().enable()
    ui.colors(primary=ACCENT_BLUE, dark=BG, dark_page=BG, positive=ACCENT_GREEN, negative=ACCENT_RED, warning=ACCENT_AMBER)
    ui.add_head_html(_FONT_LINKS)
    ui.add_head_html(f"<style>{_CSS}</style>")
