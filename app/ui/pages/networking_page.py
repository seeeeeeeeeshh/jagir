from nicegui import ui

from app.core.models import Contact
from app.ui.layout import page_frame
from app.ui.state import companies_repo, contacts_repo


def register():
    @ui.page("/networking")
    def networking_page():
        with page_frame("Networking", "/networking"):
            table_container = ui.column().classes("w-full")

            @ui.refreshable
            def render_table():
                table_container.clear()
                with table_container:
                    contacts = contacts_repo().list_all()
                    companies_by_id = {c.id: c for c in companies_repo().list_all()}
                    if not contacts:
                        ui.label("No contacts yet.").classes("text-[color:var(--jg-text-dim)]")
                        return
                    columns = [
                        {"name": "name", "label": "Name", "field": "name"},
                        {"name": "company", "label": "Company", "field": "company"},
                        {"name": "relationship", "label": "Relationship / status", "field": "relationship"},
                        {"name": "email", "label": "Email", "field": "email"},
                        {"name": "notes", "label": "Notes", "field": "notes"},
                    ]
                    rows = [
                        {
                            "name": c.name,
                            "company": companies_by_id.get(c.company_id).name if c.company_id in companies_by_id else "",
                            "relationship": c.relationship or "",
                            "email": c.email or "",
                            "notes": c.notes or "",
                        }
                        for c in contacts
                    ]
                    with ui.card().classes("w-full q-pa-none"):
                        ui.table(columns=columns, rows=rows, row_key="name").classes("w-full")

            def open_add_dialog():
                with ui.dialog() as dialog, ui.card().classes("w-[480px]"):
                    ui.label("Add Contact").classes("text-lg font-semibold")
                    name_input = ui.input("Name *").classes("w-full")
                    company_input = ui.input("Company").classes("w-full")
                    title_input = ui.input("Title").classes("w-full")
                    linkedin_input = ui.input("LinkedIn URL").classes("w-full")
                    email_input = ui.input("Email").classes("w-full")
                    relationship_input = ui.select(
                        [
                            "Not contacted", "Connection requested", "Connected", "Message sent",
                            "Replied", "Referral offered", "Referral submitted", "No response",
                            "Follow-up needed",
                        ],
                        label="Status",
                    ).classes("w-full")
                    notes_input = ui.textarea("Notes").classes("w-full")

                    def submit():
                        if not name_input.value:
                            ui.notify("Name is required", type="negative")
                            return
                        company_id = None
                        if company_input.value:
                            company_id = companies_repo().get_or_create(company_input.value).id
                        contacts_repo().create(
                            Contact(
                                name=name_input.value,
                                company_id=company_id,
                                title=title_input.value or None,
                                linkedin_url=linkedin_input.value or None,
                                email=email_input.value or None,
                                relationship=relationship_input.value,
                                notes=notes_input.value or None,
                            )
                        )
                        dialog.close()
                        render_table.refresh()

                    with ui.row().classes("w-full justify-end gap-2 mt-2"):
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                        ui.button("Add Contact", on_click=submit).props("unelevated")
                dialog.open()

            ui.button("+ Add Contact", on_click=open_add_dialog).props("unelevated size=sm")
            render_table()
