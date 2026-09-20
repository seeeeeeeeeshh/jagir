from nicegui import ui

from app.core.enums import (
    PRIORITY_OPTIONS,
    STATUS_OPTIONS,
    TARGET_REACH_SAFETY_OPTIONS,
)
from app.core.status_transitions import apply_status_change
from app.ui import theme
from app.ui.components.calendar_button import add_to_calendar_button
from app.ui.layout import page_frame
from app.ui.state import (
    companies_repo,
    contacts_repo,
    cycles_repo,
    interviews_repo,
    opportunities_repo,
    prep_resources_repo,
)


def register():
    @ui.page("/opportunity/{opportunity_id}")
    def detail_page(opportunity_id: int):
        opp = opportunities_repo().get(opportunity_id)
        if not opp:
            with page_frame("Not found"):
                ui.label("That opportunity no longer exists.")
                ui.link("Back to All Opportunities", "/")
            return

        company = companies_repo().get(opp.company_id) if opp.company_id else None
        company_name = company.name if company else "Unknown company"

        with page_frame(f"{opp.title} — {company_name}"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("items-center gap-3"):
                    ui.link("← Back", "/").classes("text-sm").style("color:var(--jg-text-dim);")

                    @ui.refreshable
                    def render_status_badge():
                        theme.badge(opp.status, theme.status_category(opp.status))

                    render_status_badge()

                def confirm_delete():
                    with ui.dialog() as confirm, ui.card():
                        ui.label(f'Delete "{opp.title}"?').classes("font-semibold")
                        ui.label(
                            "This removes the opportunity and everything tied only to it — "
                            "its activity timeline, logged interviews, and links to contacts/prep "
                            "resources. Contacts and prep resources themselves are not deleted. "
                            "This cannot be undone."
                        ).classes("text-sm text-[color:var(--jg-text-dim)] mt-1")
                        with ui.row().classes("w-full justify-end gap-2 mt-3"):
                            ui.button("Cancel", on_click=confirm.close).props("flat")

                            def do_delete():
                                opportunities_repo().delete(opp.id)
                                confirm.close()
                                ui.notify("Deleted.", type="positive")
                                ui.navigate.to("/")

                            ui.button("Delete", on_click=do_delete).props("outline").classes("jg-destructive")
                    confirm.open()

                ui.button("Delete", on_click=confirm_delete).props("outline size=sm").classes("jg-destructive")

            with ui.row().classes("w-full gap-6 items-start"):
                # -- left column: editable pipeline fields (user-owned) ------
                with ui.card().classes("flex-1 min-w-[320px]"):
                    ui.label("Pipeline").classes("jg-panel-title")

                    def save_field(field_name: str, value, event_desc: str | None = None):
                        setattr(opp, field_name, value)
                        opportunities_repo().update(
                            opp,
                            log_event=(field_name, event_desc) if event_desc else None,
                        )
                        ui.notify("Saved", type="positive", timeout=800)
                        render_job_info.refresh()
                        render_timeline.refresh()
                        render_status_badge.refresh()

                    _suppress_status_event = {"on": False}
                    _pending_undo = {"fn": None}

                    def run_pending_undo():
                        fn = _pending_undo["fn"]
                        if fn is not None:
                            fn()

                    def on_status_change(e):
                        if _suppress_status_event["on"]:
                            return
                        new_status = e.value
                        prior_status = opp.status
                        prior_date_applied = opp.date_applied
                        apply_status_change(opp, new_status)
                        save_field("status", new_status, f"Status changed to {new_status}")

                        def undo():
                            _suppress_status_event["on"] = True
                            status.set_value(prior_status)
                            _suppress_status_event["on"] = False
                            opp.date_applied = prior_date_applied
                            save_field("status", prior_status, f"Status reverted to {prior_status}")
                            undo_row.set_visibility(False)
                            _pending_undo["fn"] = None

                        _pending_undo["fn"] = undo
                        undo_label.set_text(f'Changed to "{new_status}".')
                        undo_row.set_visibility(True)

                        def hide_if_still_pending():
                            if _pending_undo["fn"] is undo:
                                undo_row.set_visibility(False)
                                _pending_undo["fn"] = None

                        ui.timer(6.0, hide_if_still_pending, once=True)

                    cycle_options = {
                        c.id: c.name + ("  \u00b7  archived" if c.is_archived else "") for c in cycles_repo().list_all()
                    }
                    cycle_select = ui.select(cycle_options, value=opp.cycle_id, label="Cycle").classes("w-full")
                    cycle_select.on_value_change(
                        lambda e: e.value is not None
                        and save_field("cycle_id", e.value, f"Moved to {cycle_options[e.value]}")
                    )

                    status = ui.select(STATUS_OPTIONS, value=opp.status, label="Status").classes("w-full")
                    status.on_value_change(on_status_change)

                    with ui.row().classes("items-center gap-2 -mt-2") as undo_row:
                        undo_label = ui.label().classes("text-xs text-[color:var(--jg-text-dim)]")
                        ui.button("Undo", on_click=run_pending_undo).props("flat dense size=sm")
                    undo_row.set_visibility(False)

                    priority = ui.select(PRIORITY_OPTIONS, value=opp.priority, label="Priority").classes("w-full")
                    priority.on_value_change(lambda e: save_field("priority", e.value))

                    trs = ui.select(TARGET_REACH_SAFETY_OPTIONS, value=opp.target_reach_safety, label="Target / Reach / Safety").classes("w-full")
                    trs.on_value_change(lambda e: save_field("target_reach_safety", e.value))

                    deadline = ui.input("Application deadline", value=opp.application_deadline).props("type=date").classes("w-full")
                    deadline.on_value_change(lambda e: save_field("application_deadline", e.value))
                    add_to_calendar_button(
                        f"Application deadline — {opp.title} @ {company_name}",
                        lambda: deadline.value,
                        all_day=True,
                    )

                    next_action = ui.input("Next action", value=opp.next_action).classes("w-full")
                    next_action.on_value_change(lambda e: save_field("next_action", e.value))

                    next_action_date = ui.input("Next action date", value=opp.next_action_date).props("type=date").classes("w-full")
                    next_action_date.on_value_change(lambda e: save_field("next_action_date", e.value))
                    add_to_calendar_button(
                        lambda: f"{next_action.value or 'Next action'} — {opp.title} @ {company_name}",
                        lambda: next_action_date.value,
                        all_day=True,
                    )

                    with ui.row().classes("w-full gap-2"):
                        resume_version = ui.input("Resume version", value=opp.resume_version).classes("flex-1")
                        resume_version.on_value_change(lambda e: save_field("resume_version", e.value))
                        cover_letter_version = ui.input("Cover letter version", value=opp.cover_letter_version).classes("flex-1")
                        cover_letter_version.on_value_change(lambda e: save_field("cover_letter_version", e.value))

                    notes = ui.textarea("Notes", value=opp.notes).classes("w-full")
                    notes.on_value_change(lambda e: save_field("notes", e.value))

                # -- right column: job info (LinkedIn-owned once synced, ----
                # -- otherwise whatever was entered manually) ---------------
                @ui.refreshable
                def render_job_info():
                    with ui.card().classes("flex-1 min-w-[320px]"):
                        ui.label("Job info").classes("jg-panel-title")
                        ui.label(f"Position type: {opp.position_type}").classes("text-sm")
                        ui.label(f"Location: {opp.location or '—'}").classes("text-sm")
                        ui.label(f"Workplace: {opp.workplace_type or '—'}   ·   Employment: {opp.employment_type or '—'}").classes("text-sm")
                        ui.label(f"Salary: {opp.salary_text or '—'}").classes("text-sm")
                        if opp.job_url:
                            ui.link("Job posting", opp.job_url, new_tab=True).style("color:var(--jg-blue);")
                        if opp.linkedin_url:
                            ui.link("LinkedIn listing", opp.linkedin_url, new_tab=True).style("color:var(--jg-blue);")
                        ui.label(f"Date saved: {opp.date_saved or '—'}   ·   Date applied: {opp.date_applied or '—'}").classes(
                            "jg-mono text-sm text-[color:var(--jg-text-dim)] mt-2"
                        )
                        if opp.linkedin_last_synced_at:
                            ui.label(f"Last synced from LinkedIn: {opp.linkedin_last_synced_at}").classes(
                                "jg-mono text-xs text-[color:var(--jg-text-faint)]"
                            )
                        ui.label(f"Source: {opp.source}   ·   Origin: {opp.origin}").classes(
                            "text-xs text-[color:var(--jg-text-faint)]"
                        )
                        if opp.job_description:
                            with ui.expansion("Job description"):
                                ui.label(opp.job_description).classes("whitespace-pre-wrap text-sm")

                render_job_info()

            # -- timeline --------------------------------------------------
            @ui.refreshable
            def render_timeline():
                with ui.card().classes("w-full"):
                    ui.label("Timeline").classes("jg-panel-title")
                    activity = opportunities_repo().get_activity(opp.id)
                    if not activity:
                        ui.label("No activity yet.").classes("text-sm text-[color:var(--jg-text-dim)] mt-2")
                    for event in activity:
                        with ui.row().classes("items-baseline gap-2 py-1").style("border-top: 1px solid var(--jg-border);"):
                            ui.label(event.event_date[:10]).classes("jg-mono text-xs text-[color:var(--jg-text-dim)]")
                            ui.label(event.description or event.event_type).classes("text-sm")

            render_timeline()

            # -- interviews --------------------------------------------------
            with ui.card().classes("w-full"):
                ui.label("Interviews").classes("jg-panel-title")
                interviews = interviews_repo().list_for_opportunity(opp.id)
                if not interviews:
                    ui.label("No interviews scheduled.").classes("text-sm text-[color:var(--jg-text-dim)] mt-2")
                for interview in interviews:
                    with ui.row().classes("w-full items-center justify-between mt-2"):
                        ui.label(
                            f"{interview.stage} — {interview.scheduled_at or 'unscheduled'} — {interview.outcome or 'pending'}"
                        ).classes("text-sm")
                        if interview.scheduled_at:
                            add_to_calendar_button(
                                f"{interview.stage} — {opp.title} @ {company_name}",
                                interview.scheduled_at,
                            )

            # -- contacts / networking ----------------------------------------
            with ui.card().classes("w-full"):
                ui.label("Contacts").classes("jg-panel-title")
                contacts = contacts_repo().list_for_opportunity(opp.id)
                if not contacts:
                    ui.label("No contacts linked.").classes("text-sm text-[color:var(--jg-text-dim)] mt-2")
                for contact in contacts:
                    ui.label(f"{contact.name} — {contact.relationship or 'contact'}").classes("text-sm mt-2")

            # -- prep resources ------------------------------------------------
            with ui.card().classes("w-full"):
                ui.label("Prep resources").classes("jg-panel-title")
                resources = prep_resources_repo().list_for_opportunity(opp.id)
                if not resources:
                    ui.label("No prep resources linked.").classes("text-sm text-[color:var(--jg-text-dim)] mt-2")
                for resource in resources:
                    ui.label(f"{resource.title} ({resource.category or 'uncategorized'})").classes("text-sm mt-2")
