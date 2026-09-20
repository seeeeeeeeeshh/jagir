import sqlite3

import pandas as pd

from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.contacts_repo import ContactsRepo

COLUMNS = [
    "Contact ID", "Name", "Company", "Title", "LinkedIn URL", "Relationship / Status",
    "Email", "Phone", "Notes", "Last Updated",
]


def build_networking(conn: sqlite3.Connection) -> pd.DataFrame:
    contacts = ContactsRepo(conn).list_all()
    companies_by_id = {c.id: c for c in CompaniesRepo(conn).list_all()}
    rows = [
        {
            "Contact ID": c.id,
            "Name": c.name,
            "Company": companies_by_id.get(c.company_id).name if c.company_id in companies_by_id else "",
            "Title": c.title or "",
            "LinkedIn URL": c.linkedin_url or "",
            "Relationship / Status": c.relationship or "",
            "Email": c.email or "",
            "Phone": c.phone or "",
            "Notes": c.notes or "",
            "Last Updated": c.updated_at or "",
        }
        for c in contacts
    ]
    return pd.DataFrame(rows, columns=COLUMNS)
