from datetime import date

from nicegui import ui

from app.analytics.cycle_stats import summarize_cycle
from app.core.cycles import TERMS, cycle_name, term_dates, term_for_month
from app.core.models import Cycle
from app.ui import theme
from app.ui.layout import page_frame
from app.ui.state import cycles_repo, opportunities_repo

_CUSTOM = "Custom"


def _date_range(cycle: Cycle) -> str:
    if cycle.start_date and cycle.end_date:
        return f"{cycle.start_date}  →  {cycle.end_date}"
    return cycle.start_date or cycle.end_date or "No dates set"


def register():
    @ui.page("/cycles")
    def cycles_page():
        with page_frame("Cycles", "/cycles"):
            ui.label(
                "A cycle is one application season. Finished ones can be archived: they drop out of "
                "your lists and dashboard but keep all their history, and you can reopen them anytime."
            ).classes("text-sm text-[color:var(--jg-text-dim)]")

            # -- actions ----------------------------------------------------

            def open_cycle(cycle_id: int):
                cycles_repo().set_view(cycle_id)
                ui.navigate.to("/")

            def open_new_cycle_dialog():
                repo = cycles_repo()
                all_cycles = repo.list_all()
                active = [c for c in all_cycles if not c.is_archived]
                newest = all_cycles[0] if all_cycles else None

                # Default to "same season, next year" (Fall 2026 -> Fall 2027):
                # the recurring pattern this app was asked to support.
                if newest and newest.start_date:
                    seed_year = int(newest.start_date[:4]) + 1
                    seed_term = term_for_month(int(newest.start_date[5:7]))
                else:
                    seed_year = date.today().year
                    seed_term = term_for_month(date.today().month)

                with ui.dialog() as dialog, ui.card().classes("w-[460px] max-w-full"):
                    ui.label("New cycle").classes("text-lg font-semibold")
                    with ui.row().classes("w-full gap-4"):
                        term_select = ui.select([*TERMS, _CUSTOM], value=seed_term, label="Season").classes("flex-1")
                        year_input = ui.number("Year", value=seed_year, format="%d", precision=0).classes("flex-1")
                    name_input = ui.input("Name", value=cycle_name(seed_term, seed_year)).classes("w-full")
                    seed_start, seed_end = term_dates(seed_term, seed_year)
                    with ui.row().classes("w-full gap-4"):
                        start_input = ui.input("Starts", value=seed_start).props("type=date").classes("flex-1")
                        end_input = ui.input("Ends", value=seed_end).props("type=date").classes("flex-1")

                    def refill(_=None):
                        if term_select.value == _CUSTOM or not year_input.value:
                            return
                        year = int(year_input.value)
                        name_input.value = cycle_name(term_select.value, year)
                        start_input.value, end_input.value = term_dates(term_select.value, year)

                    term_select.on_value_change(refill)
                    year_input.on_value_change(refill)

                    switch_now = ui.checkbox("Switch to it now", value=True)

                    # Pre-tick "archive the old one" only when the old cycle
                    # is plainly over (ended before the new one starts), so
                    # running two seasons side by side isn't broken by default.
                    archive_boxes: list[tuple[ui.checkbox, Cycle]] = []
                    for old in active:
                        over = bool(old.end_date) and old.end_date < seed_start
                        box = ui.checkbox(f"Archive {old.name} (finished)", value=over)
                        archive_boxes.append((box, old))

                    error_label = ui.label("").style("color:var(--jg-red);")

                    def create():
                        try:
                            created = repo.create(name_input.value, start_input.value, end_input.value)
                        except ValueError as exc:
                            error_label.text = str(exc)
                            return
                        for box, old in archive_boxes:
                            if box.value:
                                repo.archive(old.id)
                        if switch_now.value:
                            repo.set_view(created.id)
                        dialog.close()
                        ui.notify(f"Created {created.name}.", type="positive")
                        ui.navigate.reload()

                    with ui.row().classes("w-full justify-end gap-2 mt-2"):
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                        ui.button("Create cycle", on_click=create).props("unelevated")
                dialog.open()

            def open_edit_dialog(cycle: Cycle):
                with ui.dialog() as dialog, ui.card().classes("w-[460px] max-w-full"):
                    ui.label(f"Edit {cycle.name}").classes("text-lg font-semibold")
                    name_input = ui.input("Name", value=cycle.name).classes("w-full")
                    with ui.row().classes("w-full gap-4"):
                        start_input = ui.input("Starts", value=cycle.start_date).props("type=date").classes("flex-1")
                        end_input = ui.input("Ends", value=cycle.end_date).props("type=date").classes("flex-1")
                    error_label = ui.label("").style("color:var(--jg-red);")

                    def save():
                        try:
                            cycles_repo().update(cycle.id, name_input.value, start_input.value, end_input.value)
                        except ValueError as exc:
                            error_label.text = str(exc)
                            return
                        dialog.close()
                        ui.navigate.reload()

                    with ui.row().classes("w-full justify-end gap-2 mt-2"):
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                        ui.button("Save", on_click=save).props("unelevated")
                dialog.open()

            def open_archive_dialog(cycle: Cycle):
                summary = summarize_cycle(opportunities_repo().list_all(cycle_id=cycle.id))
                with ui.dialog() as dialog, ui.card().classes("w-[460px] max-w-full"):
                    ui.label(f"Archive {cycle.name}?").classes("font-semibold")
                    if summary.still_open:
                        ui.label(
                            f"{summary.still_open} application(s) here are still awaiting a final outcome. "
                            "They'll be hidden from your lists, dashboard and Needs attention while archived."
                        ).classes("text-sm mt-1").style("color:var(--jg-amber);")
                    ui.label(
                        "Nothing is deleted. You can still open it from the Cycle picker or this page, "
                        "and unarchive it whenever you like."
                    ).classes("text-sm text-[color:var(--jg-text-dim)] mt-1")

                    def do_archive():
                        repo = cycles_repo()
                        repo.archive(cycle.id)
                        # Don't leave the user staring at the cycle they just put away.
                        if repo.view_cycle_id() == cycle.id:
                            remaining = repo.list_all(include_archived=False)
                            if remaining:
                                repo.set_view(remaining[0].id)
                        dialog.close()
                        ui.notify(f"Archived {cycle.name}.", type="positive")
                        ui.navigate.reload()

                    with ui.row().classes("w-full justify-end gap-2 mt-3"):
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                        ui.button("Archive", on_click=do_archive).props("unelevated")
                dialog.open()

            def do_unarchive(cycle: Cycle):
                cycles_repo().unarchive(cycle.id)
                ui.notify(f"Unarchived {cycle.name}.", type="positive")
                ui.navigate.reload()

            def do_delete(cycle: Cycle):
                try:
                    cycles_repo().delete(cycle.id)
                except ValueError as exc:
                    ui.notify(str(exc), type="warning")
                    return
                ui.navigate.reload()

            # -- rendering ------------------------------------------------------

            def render_cycle(cycle: Cycle, is_viewing: bool):
                summary = summarize_cycle(opportunities_repo().list_all(cycle_id=cycle.id))
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.row().classes("items-center gap-3"):
                            ui.label(cycle.name).classes("font-semibold").style("font-size:1.05rem;")
                            if cycle.is_archived:
                                theme.badge("Archived", "closed")
                            else:
                                theme.badge("Active", "positive")
                            if is_viewing:
                                theme.badge("Viewing", "active-early")
                        ui.label(_date_range(cycle)).classes("jg-mono text-xs text-[color:var(--jg-text-dim)]")

                    with ui.row().classes("w-full gap-0 flex-wrap mt-2"):
                        for label, value in [
                            ("Opportunities", summary.total),
                            ("Applied", summary.applied),
                            ("Interviewed", summary.interviewed),
                            ("Offers", summary.offers),
                            ("Rejected", summary.rejected),
                        ]:
                            with ui.column().classes("jg-readout").style("flex: 1 1 90px;"):
                                ui.label(str(value)).classes("jg-readout-value")
                                ui.label(label).classes("jg-readout-label")

                    with ui.row().classes("w-full items-center gap-2 mt-2"):
                        ui.button("Open", on_click=lambda c=cycle: open_cycle(c.id)).props("unelevated size=sm")
                        ui.button("Edit", on_click=lambda c=cycle: open_edit_dialog(c)).props("outline size=sm")
                        if cycle.is_archived:
                            ui.button("Unarchive", on_click=lambda c=cycle: do_unarchive(c)).props("outline size=sm")
                        else:
                            ui.button("Archive", on_click=lambda c=cycle: open_archive_dialog(c)).props("outline size=sm")
                        if summary.total == 0:
                            ui.button("Delete", on_click=lambda c=cycle: do_delete(c)).props("outline size=sm").classes(
                                "jg-destructive"
                            )

            repo = cycles_repo()
            repo.ensure_default()
            cycles = repo.list_all()
            view_id = repo.view_cycle_id()
            active = [c for c in cycles if not c.is_archived]
            archived = [c for c in cycles if c.is_archived]

            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Active").classes("jg-panel-title")
                ui.button("+ New cycle", on_click=open_new_cycle_dialog).props("unelevated size=sm")
            if active:
                for cycle in active:
                    render_cycle(cycle, cycle.id == view_id)
            else:
                ui.label("No active cycles. Create one to start tracking a new season.").classes(
                    "text-sm text-[color:var(--jg-text-dim)]"
                )

            if archived:
                ui.label("Archived").classes("jg-panel-title mt-2")
                for cycle in archived:
                    render_cycle(cycle, cycle.id == view_id)
