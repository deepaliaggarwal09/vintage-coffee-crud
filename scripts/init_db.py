"""
Create the schema and load the CA 1 data into whatever MySQL server your
credentials point at (local XAMPP or a cloud database).

    python scripts/init_db.py            # schema + data   (DROPS and recreates the tables)
    python scripts/init_db.py --schema   # schema only
    python scripts/init_db.py --data     # data only (tables must be empty)

Credentials come from .streamlit/secrets.toml or DB_* environment variables.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app import db  # noqa: E402


def split_statements(sql: str):
    """Split a .sql file into single statements (no ';' appears inside our string literals)."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    for stmt in "\n".join(lines).split(";"):
        stmt = stmt.strip()
        if stmt:
            yield stmt


def run_file(path: Path) -> int:
    n = 0
    with db.get_engine().begin() as conn:
        for stmt in split_statements(path.read_text(encoding="utf-8")):
            conn.execute(text(stmt))
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--schema", action="store_true", help="only run sql/schema.sql")
    ap.add_argument("--data", action="store_true", help="only run sql/data.sql")
    a = ap.parse_args()
    do_schema = a.schema or not a.data
    do_data = a.data or not a.schema

    try:
        db.check_connection()
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Could not connect: {db.friendly_error(exc)}\n({exc})")
    print("Connected to MySQL OK")

    if do_schema:
        print(f"schema.sql: {run_file(ROOT / 'sql' / 'schema.sql')} statements executed")
    if do_data:
        print(f"data.sql  : {run_file(ROOT / 'sql' / 'data.sql')} statements executed")

    tables = ["fiscal_years", "quarters", "companies", "annual_pnl", "balance_sheet",
              "cash_flows", "ratios", "quarterly_results", "shareholding_pattern",
              "peer_comparison"]
    print("\nRow counts:")
    for t in tables:
        print(f"  {t:<22}{db.scalar(f'SELECT COUNT(*) FROM {t}')}")


if __name__ == "__main__":
    main()
