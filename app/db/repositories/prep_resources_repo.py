import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.core.models import PrepResource


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PrepResourcesRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, resource: PrepResource) -> PrepResource:
        now = _now()
        resource.created_at = now
        resource.updated_at = now
        cur = self.conn.execute(
            "INSERT INTO prep_resources (title, category, url_or_path, notes, tags, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (
                resource.title, resource.category, resource.url_or_path, resource.notes,
                resource.tags, resource.created_at, resource.updated_at,
            ),
        )
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, resource_id: int) -> Optional[PrepResource]:
        row = self.conn.execute("SELECT * FROM prep_resources WHERE id = ?", (resource_id,)).fetchone()
        return PrepResource.from_row(row)

    def update(self, resource: PrepResource) -> PrepResource:
        resource.updated_at = _now()
        self.conn.execute(
            "UPDATE prep_resources SET title=?, category=?, url_or_path=?, notes=?, tags=?, "
            "updated_at=? WHERE id=?",
            (
                resource.title, resource.category, resource.url_or_path, resource.notes,
                resource.tags, resource.updated_at, resource.id,
            ),
        )
        self.conn.commit()
        return self.get(resource.id)

    def list_all(self) -> list[PrepResource]:
        rows = self.conn.execute("SELECT * FROM prep_resources ORDER BY category, title").fetchall()
        return [PrepResource.from_row(r) for r in rows]

    def link_to_opportunity(self, opportunity_id: int, resource_id: int) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO opportunity_prep_resources (opportunity_id, prep_resource_id) "
            "VALUES (?, ?)",
            (opportunity_id, resource_id),
        )
        self.conn.commit()

    def list_for_opportunity(self, opportunity_id: int) -> list[PrepResource]:
        rows = self.conn.execute(
            "SELECT p.* FROM prep_resources p JOIN opportunity_prep_resources opr "
            "ON p.id = opr.prep_resource_id WHERE opr.opportunity_id = ?",
            (opportunity_id,),
        ).fetchall()
        return [PrepResource.from_row(r) for r in rows]
