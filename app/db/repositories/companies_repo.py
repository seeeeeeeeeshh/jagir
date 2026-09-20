import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.core.models import Company


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonicalize(name: str) -> str:
    """Lowercase and strip common legal suffixes so 'Acme Inc.' and 'ACME'
    resolve to the same company for dedupe purposes."""
    n = name.strip().lower()
    for suffix in (" inc.", " inc", " llc", " ltd.", " ltd", " corp.", " corp", " co."):
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
    return n


class CompaniesRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_or_create(self, name: str) -> Company:
        canonical = canonicalize(name)
        row = self.conn.execute(
            "SELECT * FROM companies WHERE canonical_name = ?", (canonical,)
        ).fetchone()
        if row:
            return Company.from_row(row)

        now = _now()
        cur = self.conn.execute(
            "INSERT INTO companies (name, canonical_name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (name, canonical, now, now),
        )
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, company_id: int) -> Optional[Company]:
        row = self.conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        return Company.from_row(row)

    def list_all(self) -> list[Company]:
        rows = self.conn.execute("SELECT * FROM companies ORDER BY name").fetchall()
        return [Company.from_row(r) for r in rows]

    def update(self, company: Company) -> Company:
        company.updated_at = _now()
        self.conn.execute(
            "UPDATE companies SET name=?, website=?, industry=?, notes=?, updated_at=? "
            "WHERE id=?",
            (
                company.name,
                company.website,
                company.industry,
                company.notes,
                company.updated_at,
                company.id,
            ),
        )
        self.conn.commit()
        return self.get(company.id)
