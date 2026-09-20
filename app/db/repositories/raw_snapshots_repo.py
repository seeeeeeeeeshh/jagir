import sqlite3
from datetime import datetime, timedelta, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RawSnapshotsRepo:
    """Stores raw scraped HTML/JSON for debugging. Writes here are gated by
    RAW_SNAPSHOT_MODE in the sync orchestrator, not by this repo — this class
    just persists whatever it's given.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, sync_run_id: int, page_type: str, raw_content: str, url: str | None = None, opportunity_id: int | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO raw_snapshots (sync_run_id, opportunity_id, page_type, url, "
            "raw_html_or_json, captured_at) VALUES (?,?,?,?,?,?)",
            (sync_run_id, opportunity_id, page_type, url, raw_content, _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def prune_older_than(self, retention_days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat(timespec="seconds")
        cur = self.conn.execute("DELETE FROM raw_snapshots WHERE captured_at < ?", (cutoff,))
        self.conn.commit()
        return cur.rowcount
