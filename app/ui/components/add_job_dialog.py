from datetime import date

from nicegui import ui

from app.core.enums import (
    EMPLOYMENT_TYPE_OPTIONS,
    POSITION_TYPE_OPTIONS,
    PRIORITY_OPTIONS,
    SOURCE_OPTIONS,
    STATUS_OPTIONS,
    TARGET_REACH_SAFETY_OPTIONS,
    WORKPLACE_TYPE_OPTIONS,
)
from app.core.models import Opportunity
from app.ui.state import companies_repo, cycles_repo, opportunities_repo


def open_add_job_dialog(on_created=None):
    """Manual opportunities are first-class: this dialog is the single entry
    point for adding a job/research/RA/referral/etc. record by hand, and the
    resulting row behaves identically to a LinkedIn-imported one everywhere
    in the app.
    """
    cycles = cycles_repo().list_all()
    cycle_options = {c.id: c.name + ("  \u00b7  archived" if c.is_archived else "") for c in cycles}
    section_style = "border-top: 1px solid var(--jg-border); padding-top: .85rem; margin-top: .85rem;"

    with ui.dialog() as dialog, ui.card().classes("w-[600px] max-w-full"):
        ui.label("Add Opportunity").classes("text-lg font-semibold")

        # -- what / where -------------------------------------------------
        with ui.column().classes("w-full gap-3"):
            ui.label("What & where").classes("jg-panel-title")
            title_input = ui.input("Title *").classes("w-full")
            company_input = ui.input("Company *").classes("w-full")
            location_input = ui.input("Location").classes("w-full")
            job_url_input = ui.input("Job URL").classes("w-full")
            with ui.row().classes("w-full gap-4"):
                position_type = ui.select(POSITION_TYPE_OPTIONS, value="Internship", label="Position type").classes("flex-1")
                source = ui.select(SOURCE_OPTIONS, value="manual", label="Source").classes("flex-1")
                cycle_select = ui.select(
                    cycle_options, value=cycles_repo().capture_target_id(), label="Cycle"
                ).classes("flex-1")

        # -- status ---------------------------------------------------------
        with ui.column().classes("w-full gap-3").style(section_style):
            ui.label("Status").classes("jg-panel-title")
            with ui.row().classes("w-full gap-4"):
                status = ui.select(STATUS_OPTIONS, value="Saved", label="Status").classes("flex-1")
                priority = ui.select(PRIORITY_OPTIONS, label="Priority").classes("flex-1")
                trs = ui.select(TARGET_REACH_SAFETY_OPTIONS, label="Target / Reach / Safety").classes("flex-1")
            with ui.row().classes("w-full gap-4"):
                workplace_type = ui.select(WORKPLACE_TYPE_OPTIONS, label="Workplace").classes("flex-1")
                employment_type = ui.select(EMPLOYMENT_TYPE_OPTIONS, label="Employment type").classes("flex-1")

        # -- dates ---------------------------------------------------------
        with ui.column().classes("w-full gap-3").style(section_style):
            ui.label("Dates").classes("jg-panel-title")
            with ui.row().classes("w-full gap-4"):
                date_saved_input = ui.input("Date saved", value=date.today().isoformat()).props("type=date").classes("flex-1")
                date_applied_input = ui.input("Date applied").props("type=date").classes("flex-1")
                deadline_input = ui.input("Deadline").props("type=date").classes("flex-1")

        with ui.column().classes("w-full gap-3").style(section_style):
            notes_input = ui.textarea("Notes").classes("w-full")

        error_label = ui.label("").style("color:var(--jg-red);")

        def submit():
            if not title_input.value or not company_input.value:
                error_label.text = "Title and Company are required."
                return

            company = companies_repo().get_or_create(company_input.value)
            opp = Opportunity(
                source=source.value,
                origin="manual",
                position_type=position_type.value,
                status=status.value,
                priority=priority.value,
                target_reach_safety=trs.value,
                company_id=company.id,
                cycle_id=cycle_select.value,
                title=title_input.value,
                location=location_input.value or None,
                workplace_type=workplace_type.value,
                employment_type=employment_type.value,
                job_url=job_url_input.value or None,
                date_saved=date_saved_input.value or None,
                date_applied=date_applied_input.value or None,
                application_deadline=deadline_input.value or None,
                notes=notes_input.value or None,
            )
            created = opportunities_repo().create(opp, event_type="created", description=f"Added manually — {opp.status}")
            dialog.close()
            ui.notify(f"Added {created.title} at {company.name}", type="positive")
            if on_created:
                on_created(created)

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Add Opportunity", on_click=submit).props("unelevated")

    dialog.open()
