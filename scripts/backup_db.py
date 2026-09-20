"""Back up the database plus a full Excel export, both timestamped into
data/backups/. Uses sqlite3's own online backup API (not a raw file copy)
so it's safe to run while Jagir is running and mid-write. Usage:
    python scripts/backup_db.py
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.db.database import init_database
from app.excel.export import export_workbook


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backups_dir = settings.database_abs_path.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    source_conn = init_database(settings.database_abs_path)

    db_backup_path = backups_dir / f"job_tracker_{timestamp}.db"
    dest_conn = sqlite3.connect(db_backup_path)
    with dest_conn:
        source_conn.backup(dest_conn)
    dest_conn.close()
    print(f"Database backed up to {db_backup_path}")

    excel_backup_path = backups_dir / f"jagir_export_{timestamp}.xlsx"
    export_workbook(source_conn, excel_backup_path)
    print(f"Excel export saved to {excel_backup_path}")

    source_conn.close()


if __name__ == "__main__":
    main()
