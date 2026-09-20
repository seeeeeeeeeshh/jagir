import sqlite3

import pandas as pd

from app.db.repositories.prep_resources_repo import PrepResourcesRepo

COLUMNS = ["Resource ID", "Title", "Category", "URL / Path", "Tags", "Notes", "Last Updated"]


def build_prep_resources(conn: sqlite3.Connection) -> pd.DataFrame:
    resources = PrepResourcesRepo(conn).list_all()
    rows = [
        {
            "Resource ID": r.id,
            "Title": r.title,
            "Category": r.category or "",
            "URL / Path": r.url_or_path or "",
            "Tags": r.tags or "",
            "Notes": r.notes or "",
            "Last Updated": r.updated_at or "",
        }
        for r in resources
    ]
    return pd.DataFrame(rows, columns=COLUMNS)
