import sqlite3
from datetime import date, datetime, timezone
from typing import Optional

from app.core.cycles import default_cycle_for
from app.core.models import Cycle

# app_settings keys.
_VIEW_KEY = "current_cycle_id"   # a cycle id, or VIEW_ALL
_LAST_KEY = "last_cycle_id"      # last *specific* cycle chosen; where new records go while viewing "all"

VIEW_ALL = "all"

# Newest season first; a cycle with no start date sorts after ones that have one.
_ORDER = "ORDER BY is_archived, (start_date IS NULL), start_date DESC, id DESC"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CyclesRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- crud ---------------------------------------------------------------

    def list_all(self, include_archived: bool = True) -> list[Cycle]:
        where = "" if include_archived else "WHERE is_archived = 0"
        rows = self.conn.execute(f"SELECT * FROM cycles {where} {_ORDER}").fetchall()
        return [Cycle.from_row(r) for r in rows]

    def get(self, cycle_id: int) -> Optional[Cycle]:
        row = self.conn.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
        return Cycle.from_row(row)

    def get_by_name(self, name: str) -> Optional[Cycle]:
        row = self.conn.execute(
            "SELECT * FROM cycles WHERE name = ? COLLATE NOCASE", (name.strip(),)
        ).fetchone()
        return Cycle.from_row(row)

    def create(self, name: str, start_date: str | None = None, end_date: str | None = None) -> Cycle:
        name = (name or "").strip()
        if not name:
            raise ValueError("A cycle needs a name.")
        if self.get_by_name(name):
            raise ValueError(f'A cycle named "{name}" already exists.')
        cur = self.conn.execute(
            "INSERT INTO cycles (name, start_date, end_date, created_at) VALUES (?, ?, ?, ?)",
            (name, start_date or None, end_date or None, _now()),
        )
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get_or_create(self, name: str) -> Cycle:
        return self.get_by_name(name) or self.create(name)

    def update(self, cycle_id: int, name: str, start_date: str | None, end_date: str | None) -> Cycle:
        name = (name or "").strip()
        if not name:
            raise ValueError("A cycle needs a name.")
        clash = self.get_by_name(name)
        if clash and clash.id != cycle_id:
            raise ValueError(f'A cycle named "{name}" already exists.')
        self.conn.execute(
            "UPDATE cycles SET name = ?, start_date = ?, end_date = ? WHERE id = ?",
            (name, start_date or None, end_date or None, cycle_id),
        )
        self.conn.commit()
        return self.get(cycle_id)

    def archive(self, cycle_id: int) -> None:
        self.conn.execute(
            "UPDATE cycles SET is_archived = 1, archived_at = ? WHERE id = ?", (_now(), cycle_id)
        )
        self.conn.commit()

    def unarchive(self, cycle_id: int) -> None:
        self.conn.execute("UPDATE cycles SET is_archived = 0, archived_at = NULL WHERE id = ?", (cycle_id,))
        self.conn.commit()

    def opportunity_count(self, cycle_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM opportunities WHERE cycle_id = ?", (cycle_id,)
        ).fetchone()[0]

    def delete(self, cycle_id: int) -> None:
        """Only an empty cycle can be deleted. Deleting one that still holds
        opportunities would either orphan them or silently destroy them;
        archive it instead, or move its opportunities out first."""
        if self.opportunity_count(cycle_id):
            raise ValueError("This cycle still has opportunities in it — archive it instead, or move them first.")
        self.conn.execute("DELETE FROM cycles WHERE id = ?", (cycle_id,))
        self.conn.execute("DELETE FROM app_settings WHERE key IN (?, ?) AND value = ?", (_VIEW_KEY, _LAST_KEY, str(cycle_id)))
        self.conn.commit()

    # -- settings -----------------------------------------------------------

    def _get_setting(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    # -- which cycle is selected / where new records go -----------------------

    def ensure_default(self, today: date | None = None) -> Cycle:
        """Guarantees at least one cycle exists (a brand-new database has
        none), creating one for the season containing `today`."""
        existing = self.list_all(include_archived=True)
        if existing:
            return existing[0]
        name, start, end = default_cycle_for(today or date.today())
        return self.create(name, start, end)

    def _newest_active(self) -> Cycle | None:
        active = self.list_all(include_archived=False)
        return active[0] if active else None

    def view_cycle_id(self) -> int | None:
        """The cycle the UI is currently scoped to, or None for "all
        cycles". Falls back to the newest active cycle when nothing valid
        has been chosen yet (fresh database, or the chosen cycle was
        deleted)."""
        raw = self._get_setting(_VIEW_KEY)
        if raw == VIEW_ALL:
            return None
        if raw and raw.isdigit() and self.get(int(raw)):
            return int(raw)
        fallback = self._newest_active() or self.ensure_default()
        return fallback.id

    def set_view(self, cycle_id: int | None) -> None:
        """Select a specific cycle, or None for "all cycles"."""
        if cycle_id is None:
            self._set_setting(_VIEW_KEY, VIEW_ALL)
            return
        if not self.get(cycle_id):
            raise ValueError(f"No cycle with id {cycle_id}.")
        self._set_setting(_VIEW_KEY, str(cycle_id))
        self._set_setting(_LAST_KEY, str(cycle_id))

    def capture_target_id(self) -> int:
        """Where a new opportunity goes when nothing says otherwise (LinkedIn
        capture, Excel rows without a Cycle, tests, ...). The selected cycle
        if it's still open; else the last one worked in; else the newest
        open cycle. Never an archived cycle unless every cycle is archived."""
        selected = self.view_cycle_id()
        for candidate_id in (selected, self._last_worked_id()):
            if candidate_id:
                cycle = self.get(candidate_id)
                if cycle and not cycle.is_archived:
                    return cycle.id
        newest = self._newest_active()
        if newest:
            return newest.id
        return self.ensure_default().id

    def _last_worked_id(self) -> int | None:
        raw = self._get_setting(_LAST_KEY)
        return int(raw) if raw and raw.isdigit() else None
