import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.core.models import DuplicateCandidate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DuplicateCandidatesRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, candidate: DuplicateCandidate) -> DuplicateCandidate:
        candidate.created_at = _now()
        cur = self.conn.execute(
            "INSERT INTO duplicate_candidates (new_record_payload_json, "
            "candidate_opportunity_id, confidence, reason, status, sync_run_id, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                candidate.new_record_payload_json, candidate.candidate_opportunity_id,
                candidate.confidence, candidate.reason, candidate.status,
                candidate.sync_run_id, candidate.created_at,
            ),
        )
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, candidate_id: int) -> Optional[DuplicateCandidate]:
        row = self.conn.execute(
            "SELECT * FROM duplicate_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        return DuplicateCandidate.from_row(row)

    def list_pending(self) -> list[DuplicateCandidate]:
        rows = self.conn.execute(
            "SELECT * FROM duplicate_candidates WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [DuplicateCandidate.from_row(r) for r in rows]

    def resolve(self, candidate_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE duplicate_candidates SET status=?, resolved_at=? WHERE id=?",
            (status, _now(), candidate_id),
        )
        self.conn.commit()
