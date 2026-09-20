import json
from dataclasses import fields

from nicegui import ui

from app.dedupe.apply import opportunity_from_scraped
from app.dedupe.merge import merge_linkedin_fields
from app.sync.scraped_types import ScrapedJob
from app.ui import theme
from app.ui.state import companies_repo, duplicate_candidates_repo, opportunities_repo

# Only these fields are meaningful when rebuilding a ScrapedJob from a stored
# duplicate_candidates payload — extra keys (list_type, or anything else if
# the schema drifts later) should never crash the review panel.
_SCRAPED_JOB_FIELDS = {f.name for f in fields(ScrapedJob)}


def _payload_to_scraped_job(payload_json: str) -> ScrapedJob:
    payload = json.loads(payload_json)
    return ScrapedJob(**{k: v for k, v in payload.items() if k in _SCRAPED_JOB_FIELDS})


def _payload_list_type(payload_json: str) -> str:
    return json.loads(payload_json).get("list_type", "saved")


def render_duplicate_review_panel():
    """A 'possible duplicate' shows the scraped LinkedIn record next to the
    existing opportunity it fuzzy-matched, and asks the user to confirm
    whether it's the same job (merge) or a different one (keep both)."""

    @ui.refreshable
    def panel():
        candidates = duplicate_candidates_repo().list_pending()
        with ui.card().classes("w-full"):
            ui.label("Pending duplicates").classes("jg-panel-title")
            if not candidates:
                ui.label("No possible duplicates waiting for review.").classes(
                    "text-sm text-[color:var(--jg-text-dim)] mt-2"
                )
                return

            for candidate in candidates:
                scraped = _payload_to_scraped_job(candidate.new_record_payload_json)
                existing = opportunities_repo().get(candidate.candidate_opportunity_id)
                if existing is None:
                    # The matched record was deleted since this candidate was created.
                    duplicate_candidates_repo().resolve(candidate.id, "confirmed_distinct")
                    continue

                with ui.column().classes("w-full gap-2 py-3").style("border-top: 1px solid var(--jg-border);"):
                    if candidate.confidence is not None:
                        theme.badge(f"{candidate.confidence * 100:.0f}% match", "attention")
                    ui.label(candidate.reason or "Possible duplicate").classes(
                        "text-xs text-[color:var(--jg-text-dim)]"
                    )

                    with ui.row().classes("w-full gap-6 items-start flex-wrap"):
                        with ui.column().classes("flex-1 min-w-[240px] gap-1"):
                            ui.label("Scraped from LinkedIn").classes(
                                "text-xs uppercase tracking-wide text-[color:var(--jg-text-dim)]"
                            )
                            ui.label(scraped.title).classes("font-semibold")
                            ui.label(scraped.company_name).classes("text-sm text-[color:var(--jg-text-dim)]")

                        with ui.column().classes("flex-1 min-w-[240px] gap-1"):
                            ui.label("Existing record").classes(
                                "text-xs uppercase tracking-wide text-[color:var(--jg-text-dim)]"
                            )
                            ui.link(existing.title, f"/opportunity/{existing.id}").classes(
                                "font-semibold no-underline"
                            ).style("color:var(--jg-text);")
                            theme.badge(existing.status, theme.status_category(existing.status))

                    def merge_same(candidate=candidate, scraped=scraped, existing=existing):
                        fresh = opportunities_repo().get(existing.id)
                        merged = merge_linkedin_fields(fresh, scraped)
                        merged.needs_review = 0
                        merged.review_reason = None
                        merged.match_confidence = None
                        opportunities_repo().update(
                            merged, log_event=("linkedin_sync", "Confirmed duplicate — merged from LinkedIn sync")
                        )
                        duplicate_candidates_repo().resolve(candidate.id, "confirmed_merge")
                        ui.notify("Merged.", type="positive")
                        panel.refresh()

                    def keep_both(candidate=candidate, scraped=scraped, existing=existing):
                        company = companies_repo().get_or_create(scraped.company_name)
                        list_type = _payload_list_type(candidate.new_record_payload_json)
                        opportunities_repo().create(
                            opportunity_from_scraped(scraped, company.id, list_type),
                            event_type="linkedin_sync",
                            description=f"Imported from LinkedIn — confirmed distinct from {existing.title}",
                        )
                        fresh_existing = opportunities_repo().get(existing.id)
                        fresh_existing.needs_review = 0
                        fresh_existing.review_reason = None
                        fresh_existing.match_confidence = None
                        opportunities_repo().update(fresh_existing)
                        duplicate_candidates_repo().resolve(candidate.id, "confirmed_distinct")
                        ui.notify("Kept both as separate opportunities.", type="positive")
                        panel.refresh()

                    with ui.row().classes("gap-2 mt-1"):
                        ui.button("Same job — merge", on_click=merge_same).props("unelevated size=sm")
                        ui.button("Different job — keep both", on_click=keep_both).props("outline size=sm")

    panel()
    return panel
