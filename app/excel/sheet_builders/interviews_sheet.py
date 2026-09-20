import sqlite3

import pandas as pd

from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.interviews_repo import InterviewsRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo

COLUMNS = [
    "Interview ID", "Application ID", "Company", "Role", "Stage", "Scheduled At",
    "Completed At", "Outcome", "Prep Notes", "Feedback Notes",
]


def build_interviews(conn: sqlite3.Connection) -> pd.DataFrame:
    interviews = InterviewsRepo(conn).list_all()
    opportunities_repo = OpportunitiesRepo(conn)
    companies_by_id = {c.id: c for c in CompaniesRepo(conn).list_all()}

    rows = []
    for interview in interviews:
        opp = opportunities_repo.get(interview.opportunity_id)
        company = companies_by_id.get(opp.company_id) if opp and opp.company_id else None
        rows.append(
            {
                "Interview ID": interview.id,
                "Application ID": interview.opportunity_id,
                "Company": company.name if company else "",
                "Role": opp.title if opp else "",
                "Stage": interview.stage,
                "Scheduled At": interview.scheduled_at or "",
                "Completed At": interview.completed_at or "",
                "Outcome": interview.outcome or "",
                "Prep Notes": interview.prep_notes or "",
                "Feedback Notes": interview.feedback_notes or "",
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)
