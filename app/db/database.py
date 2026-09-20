import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # NiceGUI may dispatch handlers off the main thread; the app serializes all
    # DB access through the single shared connection in app/ui/state.py, so a
    # cross-thread connection is safe here.
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply any migration files under migrations/ not yet recorded in
    schema_migrations, in filename order. Returns the list of versions applied.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}

    newly_applied = []
    for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = migration_file.stem
        if version in applied:
            continue
        sql = migration_file.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
        conn.commit()
        newly_applied.append(version)
        logger.info("Applied migration %s", version)

    return newly_applied


def init_database(db_path: Path) -> sqlite3.Connection:
    conn = get_connection(db_path)
    run_migrations(conn)
    return conn
