from nicegui import ui

from app.core.enums import PRE_APPLICATION_STATUSES
from app.ui.layout import page_frame
from app.ui.state import companies_repo, opportunities_repo


def register():
    @ui.page("/companies")
    def companies_page():
        with page_frame("Companies", "/companies"):
            companies = companies_repo().list_all()
            opps = opportunities_repo().list_all()

            if not companies:
                ui.label("No companies yet — add an opportunity to create one automatically.").classes("text-[color:var(--jg-text-dim)]")
                return

            columns = [
                {"name": "name", "label": "Company", "field": "name"},
                {"name": "opportunities", "label": "Opportunities", "field": "opportunities"},
                {"name": "applications", "label": "Applications", "field": "applications"},
                {"name": "offers", "label": "Offers", "field": "offers"},
                {"name": "rejections", "label": "Rejections", "field": "rejections"},
            ]
            rows = []
            for c in companies:
                company_opps = [o for o in opps if o.company_id == c.id]
                rows.append(
                    {
                        "name": c.name,
                        "opportunities": len(company_opps),
                        # date_applied is frequently never captured (LinkedIn
                        # list pages don't expose it) — Status reliably is,
                        # so "left the pre-application stage" is what
                        # actually means "applied" here.
                        "applications": sum(1 for o in company_opps if o.status not in PRE_APPLICATION_STATUSES),
                        "offers": sum(1 for o in company_opps if o.status in ("Offer", "Accepted")),
                        "rejections": sum(1 for o in company_opps if o.status == "Rejected"),
                    }
                )
            with ui.card().classes("w-full q-pa-none"):
                ui.table(columns=columns, rows=rows, row_key="name").classes("w-full jg-mono-cols")
