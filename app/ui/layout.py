from datetime import datetime

from nicegui import ui

from app.ui import theme
from app.ui.state import cycles_repo

# A group heading of None renders no label — Applications/Research/Saved
# Jobs are grouped and indented under "All Opportunities" because they are
# filtered views of that same table, not separate data (design critique:
# the flat nav gave no visual signal of that relationship).
NAV_GROUPS: list[tuple[str | None, list[tuple[str, str, bool]]]] = [
    (None, [("Dashboard", "/dashboard", False), ("Cycles", "/cycles", False)]),
    (
        "Opportunities",
        [
            ("All Opportunities", "/", False),
            ("Applications", "/applications", True),
            ("Research", "/research", True),
            ("Saved Jobs", "/saved-jobs", True),
        ],
    ),
    (
        None,
        [
            ("Networking", "/networking", False),
            ("Interviews", "/interviews", False),
            ("Prep", "/prep", False),
            ("Companies", "/companies", False),
            ("Sync", "/sync", False),
            ("Calendar", "/calendar", False),
        ],
    ),
]


def _export_to_excel():
    # Imported lazily so pages that don't need Excel don't pay for the
    # pandas/openpyxl import on every page load.
    from app.config import settings
    from app.excel.export import export_workbook
    from app.ui.state import get_connection

    filename = f"jagir_export_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    output_path = settings.database_abs_path.parent / "exports" / filename
    export_workbook(get_connection(), output_path)
    ui.download(str(output_path), filename)
    ui.notify("Excel export ready — check your downloads.", type="positive")


def _open_import_dialog():
    import io

    from app.core.errors import humanize_exception
    from app.excel.importer import import_workbook
    from app.ui.state import get_connection

    with ui.dialog() as dialog, ui.card().classes("w-[480px] max-w-full"):
        ui.label("Import from Excel").classes("jg-panel-title")
        ui.label(
            "Upload a workbook exported from Jagir (edited or not). Only \"All "
            "Opportunities\", Companies, Networking, Prep Resources, and Interviews "
            "sheets are read — edits to Applications/Research/Saved Jobs aren't "
            "picked up (they're filtered views of the same rows; edit opportunities "
            "in All Opportunities instead). LinkedIn-managed fields (Role, Location, "
            "Compensation, etc.) on existing rows are never overwritten by an import."
        ).classes("text-xs text-[color:var(--jg-text-dim)] mt-2")

        result_area = ui.column().classes("w-full gap-2 mt-3")

        async def handle_upload(e):
            result_area.clear()
            with result_area:
                ui.label("Importing…").classes("text-sm text-[color:var(--jg-text-dim)]")
            content = await e.file.read()
            try:
                result = import_workbook(get_connection(), io.BytesIO(content))
            except Exception as exc:
                result_area.clear()
                with result_area:
                    ui.label(f"Import failed: {humanize_exception(exc)}").style("color:var(--jg-red);")
                return

            result_area.clear()
            with result_area:
                ui.label(result.summary_text).classes("text-sm")
                if result.skipped_sheets:
                    ui.label("Not imported (see note above): " + ", ".join(result.skipped_sheets)).classes(
                        "text-xs text-[color:var(--jg-text-dim)]"
                    )
                if result.errors:
                    with ui.column().classes("w-full gap-1 mt-1"):
                        for err in result.errors[:20]:
                            ui.label(err).classes("text-xs").style("color:var(--jg-amber);")
                        if len(result.errors) > 20:
                            ui.label(f"…and {len(result.errors) - 20} more.").classes(
                                "text-xs text-[color:var(--jg-text-dim)]"
                            )
            ui.notify(
                "Import finished" + (" with issues" if result.errors else ""),
                type="warning" if result.errors else "positive",
            )

        ui.upload(on_upload=handle_upload, auto_upload=True, max_files=1).props('accept=".xlsx"').classes(
            "w-full mt-3"
        )

        with ui.row().classes("w-full justify-end mt-3"):
            ui.button("Close", on_click=dialog.close).props("flat")

    dialog.open()


_ALL_CYCLES = "all"


def _render_cycle_switcher():
    """Workspace-style picker at the top of the sidebar: everything below it
    (lists, dashboard, new records) follows the selected cycle. Changing it
    reloads the page so every widget re-reads the new scope — simpler and
    less error-prone than threading a refresh through every page."""
    repo = cycles_repo()
    view_id = repo.view_cycle_id()
    options: dict = {c.id: c.name + ("  ·  archived" if c.is_archived else "") for c in repo.list_all()}
    options[_ALL_CYCLES] = "All cycles"

    def on_change(e):
        repo.set_view(None if e.value == _ALL_CYCLES else e.value)
        ui.navigate.reload()

    ui.label("Cycle").classes("jg-nav-group-label")
    ui.select(options, value=view_id if view_id is not None else _ALL_CYCLES, on_change=on_change).props(
        "dense outlined options-dense"
    ).classes("mx-4 jg-cycle-select").style("width: calc(100% - 2rem);").tooltip(
        "Every list, the dashboard and new opportunities follow this cycle"
    )


def _render_archived_banner():
    repo = cycles_repo()
    view_id = repo.view_cycle_id()
    cycle = repo.get(view_id) if view_id is not None else None
    if not cycle or not cycle.is_archived:
        return
    active = repo.list_all(include_archived=False)
    with ui.row().classes("w-full items-center justify-between jg-archived-banner"):
        ui.label(
            f"Viewing archived cycle: {cycle.name}. It is kept for reference and doesn't count toward your current cycle."
        ).classes("text-sm")
        if active:

            def switch_back():
                repo.set_view(active[0].id)
                ui.navigate.reload()

            ui.button(f"Switch to {active[0].name}", on_click=switch_back).props("outline size=sm")


def page_frame(title: str, active_path: str | None = None, show_data_actions: bool = True):
    theme.apply_theme()
    ui.page_title(f"Jagir — {title}")

    drawer = ui.left_drawer(fixed=True, bordered=False).classes("q-pa-none").props("breakpoint=768")
    with drawer:
        with ui.column().classes("w-full gap-0 py-4"):
            ui.label("Jagir").classes("px-4 pb-4 jg-display").style(
                "font-size:1.25rem; font-weight:600; letter-spacing:.01em; color:var(--jg-brand);"
            )
            _render_cycle_switcher()
            for group_label, items in NAV_GROUPS:
                if group_label:
                    ui.label(group_label).classes("jg-nav-group-label")
                for label, path, indented in items:
                    classes = "jg-nav-link" + (" jg-nav-active" if path == active_path else "") + (" jg-nav-indent" if indented else "")
                    ui.link(label, path).classes(classes)

    with ui.header().classes("items-center justify-between").style("padding: 0 .5rem 0 .25rem;"):
        with ui.row().classes("items-center gap-1"):
            ui.button(icon="menu", on_click=drawer.toggle).props("flat round dense")
            ui.label(title).classes("jg-panel-title").style("font-size:.85rem; color:var(--jg-text);")
        with ui.row().classes("gap-2"):

            def open_add_dialog():
                from app.ui.components.add_job_dialog import open_add_job_dialog

                open_add_job_dialog(on_created=lambda opp: ui.navigate.to(f"/opportunity/{opp.id}"))

            ui.button("+ Add Opportunity", on_click=open_add_dialog).props("unelevated size=sm")
            if show_data_actions:
                ui.button("Import from Excel", on_click=_open_import_dialog).props("outline size=sm")
                ui.button("Export to Excel", on_click=_export_to_excel).props("outline size=sm")

    content = ui.column().classes("w-full px-4 sm:px-6 py-6 gap-5")
    with content:
        _render_archived_banner()
    return content
