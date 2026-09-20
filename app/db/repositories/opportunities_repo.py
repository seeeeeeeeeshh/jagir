import sqlite3
from dataclasses import fields
from datetime import datetime, timezone
from typing import Optional

from app.core.models import ApplicationActivity, Opportunity
from app.db.repositories.cycles_repo import CyclesRepo

_WRITABLE_FIELDS = [f.name for f in fields(Opportunity) if f.name not in ("id", "created_at")]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class OpportunitiesRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- basic CRUD -----------------------------------------------------

    def create(self, opp: Opportunity, event_type: str = "created", description: str | None = None) -> Opportunity:
        now = _now()
        opp.created_at = now
        opp.updated_at = now
        if opp.cycle_id is None:
            # Every creation path (add dialog, LinkedIn capture, Excel import,
            # "keep both" on a duplicate) lands in the cycle being worked in
            # unless it says otherwise, so none of them need to know about
            # cycles.
            opp.cycle_id = CyclesRepo(self.conn).capture_target_id()

        cols = ["created_at"] + _WRITABLE_FIELDS
        placeholders = ", ".join("?" for _ in cols)
        values = [getattr(opp, c) for c in cols]
        cur = self.conn.execute(
            f"INSERT INTO opportunities ({', '.join(cols)}) VALUES ({placeholders})",
            values,
        )
        opp.id = cur.lastrowid
        self._log_activity(opp.id, event_type, description or f"{opp.status} — {opp.title}")
        self.conn.commit()
        return self.get(opp.id)

    def get(self, opportunity_id: int) -> Optional[Opportunity]:
        row = self.conn.execute(
            "SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)
        ).fetchone()
        return Opportunity.from_row(row)

    def update(self, opp: Opportunity, log_event: tuple[str, str] | None = None) -> Opportunity:
        opp.updated_at = _now()
        set_clause = ", ".join(f"{c}=?" for c in _WRITABLE_FIELDS)
        values = [getattr(opp, c) for c in _WRITABLE_FIELDS] + [opp.id]
        self.conn.execute(f"UPDATE opportunities SET {set_clause} WHERE id=?", values)
        if log_event:
            event_type, description = log_event
            self._log_activity(opp.id, event_type, description)
        self.conn.commit()
        return self.get(opp.id)

    def delete(self, opportunity_id: int) -> None:
        """Deleting an opportunity means deleting everything that only
        exists because of it (activity log, interviews, its links into
        contacts/prep resources, its raw sync snapshots, and any pending
        duplicate-candidate review naming it) — every one of those tables
        has a NOT-NULL-in-practice foreign key back to opportunities, so
        without this the delete fails outright with a FOREIGN KEY
        constraint error. Contacts and prep resources themselves are never
        deleted, only their link to this opportunity; another opportunity
        that had marked this one as its duplicate has that mark cleared,
        not itself deleted."""
        self.conn.execute("UPDATE opportunities SET duplicate_of_id = NULL WHERE duplicate_of_id = ?", (opportunity_id,))
        self.conn.execute("DELETE FROM duplicate_candidates WHERE candidate_opportunity_id = ?", (opportunity_id,))
        self.conn.execute("DELETE FROM raw_snapshots WHERE opportunity_id = ?", (opportunity_id,))
        self.conn.execute("DELETE FROM opportunity_prep_resources WHERE opportunity_id = ?", (opportunity_id,))
        self.conn.execute("DELETE FROM interviews WHERE opportunity_id = ?", (opportunity_id,))
        self.conn.execute("DELETE FROM opportunity_contacts WHERE opportunity_id = ?", (opportunity_id,))
        self.conn.execute("DELETE FROM application_activity WHERE opportunity_id = ?", (opportunity_id,))
        self.conn.execute("DELETE FROM opportunities WHERE id = ?", (opportunity_id,))
        self.conn.commit()

    # -- listing / filtering ---------------------------------------------

    def list_all(
        self,
        position_types: list[str] | None = None,
        statuses: list[str] | None = None,
        exclude_pre_application: bool = False,
        search: str | None = None,
        cycle_id: int | None = None,
    ) -> list[Opportunity]:
        query = "SELECT o.* FROM opportunities o LEFT JOIN companies c ON o.company_id = c.id WHERE 1=1"
        params: list = []

        if cycle_id is not None:
            query += " AND o.cycle_id = ?"
            params.append(cycle_id)

        if position_types:
            placeholders = ",".join("?" for _ in position_types)
            query += f" AND o.position_type IN ({placeholders})"
            params.extend(position_types)

        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            query += f" AND o.status IN ({placeholders})"
            params.extend(statuses)

        if exclude_pre_application:
            query += " AND o.status NOT IN ('Saved', 'Interested')"

        if search:
            query += " AND (o.title LIKE ? OR c.name LIKE ? OR o.location LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like])

        query += " ORDER BY o.updated_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [Opportunity.from_row(r) for r in rows]

    def list_needs_review(self) -> list[Opportunity]:
        rows = self.conn.execute(
            "SELECT * FROM opportunities WHERE needs_review = 1 ORDER BY updated_at DESC"
        ).fetchall()
        return [Opportunity.from_row(r) for r in rows]

    # -- dedupe support ---------------------------------------------------

    def find_by_linkedin_job_id(self, linkedin_job_id: str) -> Optional[Opportunity]:
        row = self.conn.execute(
            "SELECT * FROM opportunities WHERE linkedin_job_id = ?", (linkedin_job_id,)
        ).fetchone()
        return Opportunity.from_row(row)

    def find_by_canonical_url(self, canonical_url: str) -> Optional[Opportunity]:
        row = self.conn.execute(
            "SELECT * FROM opportunities WHERE canonical_linkedin_url = ?", (canonical_url,)
        ).fetchone()
        return Opportunity.from_row(row)

    def find_candidates_by_company(self, company_id: int, cycle_id: int | None = None) -> list[Opportunity]:
        query = "SELECT * FROM opportunities WHERE company_id = ?"
        params: list = [company_id]
        if cycle_id is not None:
            query += " AND cycle_id = ?"
            params.append(cycle_id)
        rows = self.conn.execute(query, params).fetchall()
        return [Opportunity.from_row(r) for r in rows]

    def move_to_cycle(self, opportunity_ids: list[int], cycle_id: int, cycle_name: str) -> int:
        """Reassign opportunities to another cycle, logging it on each one's
        timeline. Returns how many actually changed."""
        moved = 0
        for opportunity_id in opportunity_ids:
            opp = self.get(opportunity_id)
            if opp is None or opp.cycle_id == cycle_id:
                continue
            opp.cycle_id = cycle_id
            self.update(opp, log_event=("cycle", f"Moved to {cycle_name}"))
            moved += 1
        return moved

    # -- activity timeline --------------------------------------------------

    def _log_activity(self, opportunity_id: int, event_type: str, description: str, event_date: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO application_activity (opportunity_id, event_date, event_type, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (opportunity_id, event_date or _now(), event_type, description, _now()),
        )

    def log_activity(self, opportunity_id: int, event_type: str, description: str) -> None:
        self._log_activity(opportunity_id, event_type, description)
        self.conn.commit()

    def get_activity(self, opportunity_id: int) -> list[ApplicationActivity]:
        rows = self.conn.execute(
            "SELECT * FROM application_activity WHERE opportunity_id = ? ORDER BY event_date, id",
            (opportunity_id,),
        ).fetchall()
        return [ApplicationActivity.from_row(r) for r in rows]
