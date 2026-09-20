import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.core.models import Interview


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InterviewsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, interview: Interview) -> Interview:
        now = _now()
        interview.created_at = now
        interview.updated_at = now
        cur = self.conn.execute(
            "INSERT INTO interviews (opportunity_id, stage, scheduled_at, completed_at, "
            "outcome, prep_notes, feedback_notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                interview.opportunity_id, interview.stage, interview.scheduled_at,
                interview.completed_at, interview.outcome, interview.prep_notes,
                interview.feedback_notes, interview.created_at, interview.updated_at,
            ),
        )
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, interview_id: int) -> Optional[Interview]:
        row = self.conn.execute("SELECT * FROM interviews WHERE id = ?", (interview_id,)).fetchone()
        return Interview.from_row(row)

    def list_for_opportunity(self, opportunity_id: int) -> list[Interview]:
        rows = self.conn.execute(
            "SELECT * FROM interviews WHERE opportunity_id = ? ORDER BY scheduled_at",
            (opportunity_id,),
        ).fetchall()
        return [Interview.from_row(r) for r in rows]

    def list_all(self) -> list[Interview]:
        rows = self.conn.execute("SELECT * FROM interviews ORDER BY scheduled_at DESC").fetchall()
        return [Interview.from_row(r) for r in rows]

    def list_upcoming(self) -> list[Interview]:
        rows = self.conn.execute(
            "SELECT * FROM interviews WHERE completed_at IS NULL ORDER BY scheduled_at"
        ).fetchall()
        return [Interview.from_row(r) for r in rows]

    def update(self, interview: Interview) -> Interview:
        interview.updated_at = _now()
        self.conn.execute(
            "UPDATE interviews SET stage=?, scheduled_at=?, completed_at=?, outcome=?, "
            "prep_notes=?, feedback_notes=?, updated_at=? WHERE id=?",
            (
                interview.stage, interview.scheduled_at, interview.completed_at,
                interview.outcome, interview.prep_notes, interview.feedback_notes,
                interview.updated_at, interview.id,
            ),
        )
        self.conn.commit()
        return self.get(interview.id)
