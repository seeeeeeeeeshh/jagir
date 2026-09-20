# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

NiceGUI (Python, Quasar/Vue under the hood) + Tailwind utility classes via NiceGUI's `.classes()`, backed by SQLite. Existing codebase; not greenfield.

## Users

A single user: the app's own author, tracking their own job/internship/research-position search. Run locally, single session, no auth, no multi-tenancy. (Confirmed: not designing for sharing or other job-seekers.)

## Product Purpose

A local-first job & opportunity tracker unifying applications, saved jobs, research/RA positions, networking contacts, interviews, and prep resources in one SQLite database, so the user has a single system of record for their job search instead of scattering it across spreadsheets, browser tabs, and notes. LinkedIn sync (via the user's own logged-in Playwright session) and Excel import/export are planned to sit on top of the same database without becoming the source of truth themselves.

## Positioning

SQLite is the single source of truth; Excel/CSV are import/export formats only, never authoritative. Every opportunity record splits LinkedIn-owned fields (which sync may overwrite) from user-owned fields — status, priority, notes, networking, prep — which sync must never touch. This ownership split is the thing a plain spreadsheet or a raw LinkedIn export can't give the user: durable personal judgment layered on top of resyncable external data.

## Operating Context

Used solo, at a desk, likely returning to it daily/several times a week during an active search: checking pipeline status, adding a job just found, logging an interview, jotting networking follow-ups. Also used in short bursts before/after interviews (prep) and in longer sessions (research/RA hunting, reviewing the funnel). Excel export exists for offline review/sharing snapshots outside the app.

## Capabilities and Constraints

Implemented: SQLite schema + migrations, manual CRUD for opportunities/contacts/interviews/prep resources, NiceGUI UI with Dashboard, All Opportunities, Applications, Research, Saved Jobs, Networking, Interviews, Prep, Companies pages, an opportunity detail view with editable pipeline fields and an activity timeline, and derived fields (days since application, deadline urgency, application health) computed at query time.

Not yet built (UI must reflect this honestly, e.g. disabled states rather than broken affordances): Excel export/import, Playwright LinkedIn sync engine, dedupe/merge engine, full analytics dashboard (funnel, time-to-response, company/role stats).

Domain vocabulary already fixed in code (`app/core/enums.py`) — treat as terminology to preserve, not relabel without reason: opportunity statuses (Saved, Interested, Preparing, Applied, OA, Recruiter Screen, Interview 1/2, Final Round, Offer, Accepted, Rejected, Withdrawn, Ghosted, On Hold), priority (Low/Medium/High), target/reach/safety, position type (Internship, Research, RA, FullTime, PartTime, Other), role category (SWE, AI/ML, Data, Quant, Research, Product, Other), workplace type (Remote/Hybrid/On-site), networking status.

## Brand Commitments

None. No existing name treatment, logo, or color commitment beyond the plain text wordmark "Jagir" currently in the header. Confirmed open for a new visual direction.

## Evidence on Hand

None beyond the app's own database once populated by the user (no seeded demo data, no testimonials/case studies — this is a personal tool, not a product with external proof points).

## Product Principles

- SQLite is truth; every other format (Excel, LinkedIn) is a view or import, never authoritative — the UI should always make it obvious which fields are safe to hand-edit versus sync-owned.
- Design for a returning power user, not a first-time visitor: optimize for fast scanning and low-friction daily updates over persuasion or onboarding ceremony.
- Be honest about what's not built yet (Sync, Excel, dedupe, full analytics) — disabled/placeholder states, not broken promises.
- One person's whole job search lives here; the tool should feel calm and trustworthy under daily, sustained use, not flashy for a single first impression.

## Accessibility & Inclusion

No specific requirement established; standard web accessibility practice applies (keyboard navigable, sufficient contrast) as a baseline given daily solo use.
