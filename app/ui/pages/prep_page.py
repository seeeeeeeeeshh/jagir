from nicegui import ui

from app.core.enums import PREP_CATEGORY_OPTIONS
from app.core.models import PrepResource
from app.ui.layout import page_frame
from app.ui.state import prep_resources_repo


def register():
    @ui.page("/prep")
    def prep_page():
        with page_frame("Preparation Resources", "/prep"):
            table_container = ui.column().classes("w-full")

            @ui.refreshable
            def render_table():
                table_container.clear()
                with table_container:
                    resources = prep_resources_repo().list_all()
                    if not resources:
                        ui.label("No prep resources yet.").classes("text-[color:var(--jg-text-dim)]")
                        return
                    columns = [
                        {"name": "title", "label": "Resource", "field": "title"},
                        {"name": "category", "label": "Category", "field": "category"},
                        {"name": "url", "label": "URL / path", "field": "url"},
                        {"name": "notes", "label": "Notes", "field": "notes"},
                    ]
                    rows = [
                        {
                            "title": r.title,
                            "category": r.category or "",
                            "url": r.url_or_path or "",
                            "notes": r.notes or "",
                        }
                        for r in resources
                    ]
                    with ui.card().classes("w-full q-pa-none"):
                        ui.table(columns=columns, rows=rows, row_key="title").classes("w-full")

            def open_add_dialog():
                with ui.dialog() as dialog, ui.card().classes("w-[480px]"):
                    ui.label("Add Prep Resource").classes("text-lg font-semibold")
                    title_input = ui.input("Title *").classes("w-full")
                    category_select = ui.select(PREP_CATEGORY_OPTIONS, label="Category").classes("w-full")
                    url_input = ui.input("URL or local path").classes("w-full")
                    notes_input = ui.textarea("Notes").classes("w-full")

                    def submit():
                        if not title_input.value:
                            ui.notify("Title is required", type="negative")
                            return
                        prep_resources_repo().create(
                            PrepResource(
                                title=title_input.value,
                                category=category_select.value,
                                url_or_path=url_input.value or None,
                                notes=notes_input.value or None,
                            )
                        )
                        dialog.close()
                        render_table.refresh()

                    with ui.row().classes("w-full justify-end gap-2 mt-2"):
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                        ui.button("Add Resource", on_click=submit).props("unelevated")
                dialog.open()

            ui.button("+ Add Resource", on_click=open_add_dialog).props("unelevated size=sm")
            render_table()
