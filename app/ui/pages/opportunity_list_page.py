from nicegui import ui

from app.core.enums import STATUS_OPTIONS
from app.core.status_transitions import apply_status_change
from app.ui.components.opportunity_table import build_grid
from app.ui.layout import page_frame
from app.ui.state import companies_repo, cycles_repo, opportunities_repo


def render_opportunity_list(
    title: str,
    position_types: list[str] | None = None,
    statuses: list[str] | None = None,
    exclude_pre_application: bool = False,
    active_path: str | None = None,
):
    """Shared body for the All Opportunities / Applications / Research / Saved
    Jobs pages — they are all just different filters over the same
    `opportunities` table (see plan: Data model)."""

    with page_frame(title, active_path):
        with ui.row().classes("w-full justify-between items-center"):
            search_input = ui.input(placeholder="Search title / company / location").classes("w-96").props(
                "outlined dense input-debounce=300"
            )
            with ui.row().classes("gap-2 items-center"):
                set_status_btn = ui.button("Set status").props("outline size=sm")
                set_status_btn.set_visibility(False)
                move_cycle_btn = ui.button("Move to cycle").props("outline size=sm")
                move_cycle_btn.set_visibility(False)
                delete_selected_btn = ui.button("Delete selected").props("outline size=sm").classes("jg-destructive")
                delete_selected_btn.set_visibility(False)
                ui.button("Refresh", on_click=lambda: render_grid.refresh()).props("outline size=sm")

        with ui.card().classes("w-full q-pa-none"):
            grid_container = ui.column().classes("w-full gap-0")

            def go_to_detail(opportunity_id: int):
                ui.navigate.to(f"/opportunity/{opportunity_id}")

            current_grid = {"ref": None}

            _GRID_FIELD_TO_ATTR = {
                "title": "title",
                "position_type": "position_type",
                "priority": "priority",
                "target_reach_safety": "target_reach_safety",
                "location": "location",
                "date_saved": "date_saved",
                "date_applied": "date_applied",
                "deadline": "application_deadline",
                "source": "source",
            }

            async def handle_cell_edit(opportunity_id: int, field: str, new_value):
                opp = opportunities_repo().get(opportunity_id)
                if opp is None:
                    ui.notify("That opportunity no longer exists.", type="negative")
                    render_grid.refresh()
                    return

                if field == "status":
                    apply_status_change(opp, new_value)
                    opportunities_repo().update(opp, log_event=("status", f"Status updated to {new_value} (table edit)"))
                else:
                    attr = _GRID_FIELD_TO_ATTR.get(field)
                    if attr is None:
                        return
                    setattr(opp, attr, new_value or None)
                    label = field.replace("_", " ").title()
                    opportunities_repo().update(opp, log_event=(field, f"{label} updated via table"))

                ui.notify("Saved", type="positive", timeout=800)
                render_grid.refresh()

            async def handle_selection_change(_e=None):
                grid = current_grid["ref"]
                if grid is None:
                    return
                selected = await grid.get_selected_rows()
                if selected:
                    delete_selected_btn.set_text(f"Delete selected ({len(selected)})")
                    delete_selected_btn.set_visibility(True)
                    set_status_btn.set_text(f"Set status ({len(selected)})")
                    set_status_btn.set_visibility(True)
                    move_cycle_btn.set_text(f"Move to cycle ({len(selected)})")
                    move_cycle_btn.set_visibility(True)
                else:
                    delete_selected_btn.set_visibility(False)
                    set_status_btn.set_visibility(False)
                    move_cycle_btn.set_visibility(False)

            async def open_set_status_dialog():
                grid = current_grid["ref"]
                if grid is None:
                    return
                selected = await grid.get_selected_rows()
                if not selected:
                    return

                with ui.dialog() as status_dialog, ui.card().classes("w-[380px] max-w-full"):
                    ui.label(f"Set status for {len(selected)} opportunity(ies)").classes("font-semibold")
                    new_status_select = ui.select(STATUS_OPTIONS, label="New status").classes("w-full mt-2")
                    ui.label(
                        "Moving out of Saved/Interested for the first time also stamps today as the "
                        "date applied, same as changing status on a single opportunity."
                    ).classes("text-xs text-[color:var(--jg-text-dim)] mt-1")
                    with ui.row().classes("w-full justify-end gap-2 mt-3"):
                        ui.button("Cancel", on_click=status_dialog.close).props("flat")

                        def do_apply():
                            new_status = new_status_select.value
                            if not new_status:
                                ui.notify("Pick a status first.", type="warning")
                                return
                            for row in selected:
                                opp = opportunities_repo().get(row["id"])
                                if opp is None:
                                    continue
                                apply_status_change(opp, new_status)
                                opportunities_repo().update(
                                    opp, log_event=("status", f"Status updated to {new_status} (bulk edit)")
                                )
                            status_dialog.close()
                            ui.notify(f"Updated {len(selected)} opportunity(ies) to {new_status}.", type="positive")
                            render_grid.refresh()

                        ui.button("Apply", on_click=do_apply).props("unelevated")
                status_dialog.open()

            set_status_btn.on_click(open_set_status_dialog)

            async def open_move_cycle_dialog():
                grid = current_grid["ref"]
                if grid is None:
                    return
                selected = await grid.get_selected_rows()
                if not selected:
                    return

                cycles = cycles_repo().list_all()
                options = {c.id: c.name + ("  \u00b7  archived" if c.is_archived else "") for c in cycles}
                with ui.dialog() as move_dialog, ui.card().classes("w-[380px] max-w-full"):
                    ui.label(f"Move {len(selected)} opportunity(ies) to another cycle").classes("font-semibold")
                    target_select = ui.select(options, label="Cycle").classes("w-full mt-2")
                    ui.label(
                        "Use this to carry a role into a new season (e.g. re-applying next year) or to "
                        "fix one that landed in the wrong cycle. The move is logged on each timeline."
                    ).classes("text-xs text-[color:var(--jg-text-dim)] mt-1")
                    with ui.row().classes("w-full justify-end gap-2 mt-3"):
                        ui.button("Cancel", on_click=move_dialog.close).props("flat")

                        def do_move():
                            target_id = target_select.value
                            if target_id is None:
                                ui.notify("Pick a cycle first.", type="warning")
                                return
                            moved = opportunities_repo().move_to_cycle(
                                [row["id"] for row in selected], target_id, cycles_repo().get(target_id).name
                            )
                            move_dialog.close()
                            ui.notify(f"Moved {moved} opportunity(ies).", type="positive")
                            render_grid.refresh()

                        ui.button("Move", on_click=do_move).props("unelevated")
                move_dialog.open()

            move_cycle_btn.on_click(open_move_cycle_dialog)

            async def confirm_delete_selected():
                grid = current_grid["ref"]
                if grid is None:
                    return
                selected = await grid.get_selected_rows()
                if not selected:
                    return

                preview_titles = ", ".join(r["title"] for r in selected[:5])
                if len(selected) > 5:
                    preview_titles += f", and {len(selected) - 5} more"

                with ui.dialog() as confirm, ui.card().classes("w-[420px] max-w-full"):
                    ui.label(f"Delete {len(selected)} opportunity(ies)?").classes("font-semibold")
                    ui.label(preview_titles).classes("text-sm text-[color:var(--jg-text-dim)] mt-1")
                    ui.label(
                        "This removes each one's activity timeline, logged interviews, and links to "
                        "contacts/prep resources. Contacts and prep resources themselves are not "
                        "deleted. This cannot be undone."
                    ).classes("text-xs text-[color:var(--jg-text-dim)] mt-2")
                    with ui.row().classes("w-full justify-end gap-2 mt-3"):
                        ui.button("Cancel", on_click=confirm.close).props("flat")

                        def do_delete():
                            for row in selected:
                                opportunities_repo().delete(row["id"])
                            confirm.close()
                            ui.notify(f"Deleted {len(selected)} opportunity(ies).", type="positive")
                            delete_selected_btn.set_visibility(False)
                            render_grid.refresh()

                        ui.button("Delete", on_click=do_delete).props("outline").classes("jg-destructive")
                confirm.open()

            delete_selected_btn.on_click(confirm_delete_selected)

            @ui.refreshable
            def render_grid():
                grid_container.clear()
                current_grid["ref"] = None
                with grid_container:
                    view_cycle_id = cycles_repo().view_cycle_id()  # None == all cycles
                    opps = opportunities_repo().list_all(
                        position_types=position_types,
                        statuses=statuses,
                        exclude_pre_application=exclude_pre_application,
                        search=search_input.value or None,
                        cycle_id=view_cycle_id,
                    )
                    companies_by_id = {c.id: c for c in companies_repo().list_all()}
                    if not opps:
                        cycle = cycles_repo().get(view_cycle_id) if view_cycle_id is not None else None
                        where = f" in {cycle.name}" if cycle else ""
                        ui.label(f"No opportunities{where} yet.").classes("text-[color:var(--jg-text-dim)] p-6")
                    else:
                        current_grid["ref"] = build_grid(
                            opps, companies_by_id, go_to_detail,
                            on_selection_change=handle_selection_change,
                            on_cell_edit=handle_cell_edit,
                            cycles_by_id={c.id: c for c in cycles_repo().list_all()},
                            show_cycle=view_cycle_id is None,
                        )

            search_input.on_value_change(lambda: render_grid.refresh())
            render_grid()
