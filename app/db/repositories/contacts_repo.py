import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.core.models import Contact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ContactsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, contact: Contact) -> Contact:
        now = _now()
        contact.created_at = now
        contact.updated_at = now
        cur = self.conn.execute(
            "INSERT INTO contacts (name, company_id, title, linkedin_url, email, phone, "
            "relationship, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                contact.name, contact.company_id, contact.title, contact.linkedin_url,
                contact.email, contact.phone, contact.relationship, contact.notes,
                contact.created_at, contact.updated_at,
            ),
        )
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, contact_id: int) -> Optional[Contact]:
        row = self.conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        return Contact.from_row(row)

    def list_all(self) -> list[Contact]:
        rows = self.conn.execute("SELECT * FROM contacts ORDER BY updated_at DESC").fetchall()
        return [Contact.from_row(r) for r in rows]

    def update(self, contact: Contact) -> Contact:
        contact.updated_at = _now()
        self.conn.execute(
            "UPDATE contacts SET name=?, company_id=?, title=?, linkedin_url=?, email=?, "
            "phone=?, relationship=?, notes=?, updated_at=? WHERE id=?",
            (
                contact.name, contact.company_id, contact.title, contact.linkedin_url,
                contact.email, contact.phone, contact.relationship, contact.notes,
                contact.updated_at, contact.id,
            ),
        )
        self.conn.commit()
        return self.get(contact.id)

    def link_to_opportunity(self, opportunity_id: int, contact_id: int, role: str = "networking") -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO opportunity_contacts (opportunity_id, contact_id, role_in_application) "
            "VALUES (?, ?, ?)",
            (opportunity_id, contact_id, role),
        )
        self.conn.commit()

    def list_for_opportunity(self, opportunity_id: int) -> list[Contact]:
        rows = self.conn.execute(
            "SELECT c.* FROM contacts c JOIN opportunity_contacts oc ON c.id = oc.contact_id "
            "WHERE oc.opportunity_id = ?",
            (opportunity_id,),
        ).fetchall()
        return [Contact.from_row(r) for r in rows]

    def list_for_opportunity_by_role(self, opportunity_id: int, role: str) -> list[Contact]:
        rows = self.conn.execute(
            "SELECT c.* FROM contacts c JOIN opportunity_contacts oc ON c.id = oc.contact_id "
            "WHERE oc.opportunity_id = ? AND oc.role_in_application = ?",
            (opportunity_id, role),
        ).fetchall()
        return [Contact.from_row(r) for r in rows]
