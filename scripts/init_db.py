"""Create the SQLite database and apply all migrations. Safe to run repeatedly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.db.database import init_database


def main():
    conn = init_database(settings.database_abs_path)
    print(f"Database ready at {settings.database_abs_path}")
    conn.close()


if __name__ == "__main__":
    main()
