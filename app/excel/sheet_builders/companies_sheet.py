import sqlite3

import pandas as pd

from app.core.enums import PRE_APPLICATION_STATUSES
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo

COLUMNS = [
    "Company", "Website", "Industry", "Opportunities", "Applications", "Interviews",
    "Offers", "Rejections", "Notes",
]


def build_companies(conn: sqlite3.Connection) -> pd.DataFrame:
    companies = CompaniesRepo(conn).list_all()
    opps = OpportunitiesRepo(conn).list_all()

    rows = []
    for c in companies:
        company_opps = [o for o in opps if o.company_id == c.id]
        rows.append(
            {
                "Company": c.name,
                "Website": c.website or "",
                "Industry": c.industry or "",
                "Opportunities": len(company_opps),
                # date_applied is frequently never captured (LinkedIn's list
                # pages don't expose it, and neither the extension nor the
                # bookmarklet fetch the detail page) — Status is the field
                # that's actually reliably populated, so "has this left the
                # pre-application stage" is what genuinely counts as
                # "applied," not "is date_applied set." Using date_applied
                # here previously meant this column silently read 0 for
                # every company regardless of real applications.
                "Applications": sum(1 for o in company_opps if o.status not in PRE_APPLICATION_STATUSES),
                "Interviews": sum(1 for o in company_opps if o.status not in ("Saved", "Interested", "Preparing", "Applied")),
                "Offers": sum(1 for o in company_opps if o.status in ("Offer", "Accepted")),
                "Rejections": sum(1 for o in company_opps if o.status == "Rejected"),
                "Notes": c.notes or "",
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)
