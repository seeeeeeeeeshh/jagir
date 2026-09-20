import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.core.models import SyncRun


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SyncRunsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def start(self) -> SyncRun:
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO sync_runs (started_at, status) VALUES (?, 'running')", (now,)
        )
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, run_id: int) -> Optional[SyncRun]:
        row = self.conn.execute("SELECT * FROM sync_runs WHERE id = ?", (run_id,)).fetchone()
        return SyncRun.from_row(row)

    def finish(self, run: SyncRun) -> SyncRun:
        run.finished_at = _now()
        self.conn.execute(
            "UPDATE sync_runs SET finished_at=?, status=?, new_saved_count=?, "
            "new_applied_count=?, updated_count=?, duplicates_flagged_count=?, "
            "errors_json=?, summary_text=? WHERE id=?",
            (
                run.finished_at, run.status, run.new_saved_count, run.new_applied_count,
                run.updated_count, run.duplicates_flagged_count, run.errors_json,
                run.summary_text, run.id,
            ),
        )
        self.conn.commit()
        return self.get(run.id)

    def list_recent(self, limit: int = 20) -> list[SyncRun]:
        rows = self.conn.execute(
            "SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [SyncRun.from_row(r) for r in rows]
