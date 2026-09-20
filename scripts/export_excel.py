"""Export the current database to an Excel workbook. Usage:
    python scripts/export_excel.py [output_path]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.db.database import init_database
from app.excel.export import export_workbook


def main():
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else settings.database_abs_path.parent / "exports" / "jagir_export.xlsx"
    conn = init_database(settings.database_abs_path)
    path = export_workbook(conn, output_path)
    print(f"Exported workbook to {path}")
    conn.close()


if __name__ == "__main__":
    main()
