---
version: 1
slug: "app-ui"
primary_target: "app/ui"
related_targets: []
---

## Scope

Whole-app redesign (Operate mode): header/nav chrome + all 9 pages (Dashboard, All Opportunities, Applications, Research, Saved Jobs, Networking, Interviews, Prep, Companies) + opportunity detail view + Add Job dialog. Single-user, local NiceGUI app. See PRODUCT.md.

## Direction contract

THESIS: The app reads as one persistent instrument panel the user operates, not a stack of pages they visit — the category default this refuses is generic rounded SaaS cards on a white ground with no spatial memory between screens.

OWN-WORLD: Graphite/near-black ground (`#15171c`-ish base, `#1c1f26` panel fill), panels divided by 1px hairline seams and one step of elevation — no drop shadows, no rounded-card-on-white pattern. Compact sans (system stack) with tabular monospaced figures for every date, count, and numeric field. Panel headers in small-caps/letter-spaced labels. Status get syntax-derived accent colors (used only for state, never decoration): e.g. cool blue for active/in-progress, amber for needs-attention/urgent, green for offer/positive, muted grey for terminal/closed. Priority (Low/Medium/High) reads as accent weight/saturation, not size gimmicks. Destructive actions (Reject, Withdraw, Delete duplicate) are outline-only by default, spatially isolated from neighboring actions, and require deliberate focus before they commit — borrowed discipline, not decoration.

STORY: The user opens the app and sees their pipeline as instrument readouts (compact counts, not big stat cards), scans a dense table for what needs attention today, and drills into one opportunity's detail panel to update status/notes/timeline without losing the surrounding navigation context.

FIRST VIEWPORT (Dashboard): persistent left/top nav shell in graphite; a compact readout strip (tabular counts, not oversized stat cards) across the top of the content panel; below it, a "needs attention" panel (urgent deadlines, needs-review duplicates) given visual priority over the raw total counts; panels tile with hairline seams, no card shadows.

FORM: chosen candidate — catalog challenger `digital-design-canon-dark-first-developer-console`, weighed against a rolled "star atlas chart" direction (won on distinctiveness/audience-id, ceded on build efficiency and per-page product clarity for a dense CRUD app) and the standing conventional-SaaS exit. Seed key `2a79ff06`, assigned index 6, this challenger judged competitive→selected by user for build efficiency and product clarity across many data-dense screens. No image generation available in this environment; build is code-led.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
