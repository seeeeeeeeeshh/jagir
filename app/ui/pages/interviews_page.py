from nicegui import ui

from app.core.enums import INTERVIEW_STAGE_OPTIONS
from app.core.models import Interview
from app.ui.components.calendar_button import add_to_calendar_button
from app.ui.layout import page_frame
from app.ui.state import companies_repo, interviews_repo, opportunities_repo


def register():
    @ui.page("/interviews")
    def interviews_page():
        with page_frame("Interviews", "/interviews"):
            table_container = ui.column().classes("w-full gap-2")

            @ui.refreshable
            def render_table():
                table_container.clear()
                with table_container:
                    interviews = interviews_repo().list_upcoming()
                    if not interviews:
                        ui.label("No upcoming interviews.").classes("text-[color:var(--jg-text-dim)]")
                        return
                    companies_by_id = {c.id: c for c in companies_repo().list_all()}
                    for interview in interviews:
                        opp = opportunities_repo().get(interview.opportunity_id)
                        company = companies_by_id.get(opp.company_id) if opp and opp.company_id else None
                        with ui.card().classes("w-full"):
                            with ui.row().classes("w-full items-center justify-between"):
                                ui.link(
                                    f"{interview.stage} — {opp.title if opp else '?'} @ {company.name if company else '?'}",
                                    f"/opportunity/{interview.opportunity_id}",
                                ).classes("font-semibold no-underline").style("color:var(--jg-text);")
                                if interview.scheduled_at:
                                    add_to_calendar_button(
                                        f"{interview.stage} — {opp.title if opp else 'Interview'}",
                                        interview.scheduled_at,
                                        description=f"{company.name if company else ''} — via Jagir",
                                    )
                            scheduled = (interview.scheduled_at or "TBD").replace("T", "  ·  ")
                            ui.label(f"Scheduled: {scheduled}").classes("jg-mono text-sm text-[color:var(--jg-text-dim)]")
                            if interview.prep_notes:
                                ui.label(f"Prep notes: {interview.prep_notes}").classes("text-sm text-[color:var(--jg-text-dim)]")

            def open_add_dialog():
                opportunities = opportunities_repo().list_all(exclude_pre_application=True)
                if not opportunities:
                    ui.notify("Add an application first before scheduling an interview.", type="warning")
                    return
                companies_by_id = {c.id: c for c in companies_repo().list_all()}
                options = {
                    o.id: f"{o.title} — {companies_by_id.get(o.company_id).name if o.company_id in companies_by_id else '?'}"
                    for o in opportunities
                }
                with ui.dialog() as dialog, ui.card().classes("w-[480px]"):
                    ui.label("Add Interview").classes("text-lg font-semibold")
                    opp_select = ui.select(options, label="Application *").classes("w-full")
                    stage_select = ui.select(INTERVIEW_STAGE_OPTIONS, value="Recruiter Screen", label="Stage").classes("w-full")
                    scheduled_input = ui.input("Scheduled at").props("type=datetime-local").classes("w-full")
                    prep_notes_input = ui.textarea("Prep notes").classes("w-full")

                    def submit():
                        if not opp_select.value:
                            ui.notify("Select an application", type="negative")
                            return
                        interviews_repo().create(
                            Interview(
                                opportunity_id=opp_select.value,
                                stage=stage_select.value,
                                scheduled_at=scheduled_input.value or None,
                                prep_notes=prep_notes_input.value or None,
                            )
                        )
                        opportunities_repo().log_activity(
                            opp_select.value, "interview_scheduled", f"{stage_select.value} interview scheduled"
                        )
                        dialog.close()
                        render_table.refresh()

                    with ui.row().classes("w-full justify-end gap-2 mt-2"):
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                        ui.button("Add Interview", on_click=submit).props("unelevated")
                dialog.open()

            ui.button("+ Add Interview", on_click=open_add_dialog).props("unelevated size=sm")
            render_table()
