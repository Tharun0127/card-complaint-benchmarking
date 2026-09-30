"""Run every query in sql/ with DuckDB and save each result to outputs/sql/<name>.csv."""
from __future__ import annotations

import sys

import duckdb

from config import CARDS_ALL_PARQUET, COMPLAINTS_PARQUET, OUTPUT_DIR, REFERENCE_DIR, SQL_DIR

SQL_OUT = OUTPUT_DIR / "sql"
VIEWS_FILE = "00_views.sql"


def connect() -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with the project views defined."""
    con = duckdb.connect()
    views = (SQL_DIR / VIEWS_FILE).read_text(encoding="utf-8")
    for key, path in {
        "{complaints_parquet}": COMPLAINTS_PARQUET,
        "{cards_all_parquet}": CARDS_ALL_PARQUET,
        "{denominators_csv}": REFERENCE_DIR / "issuer_denominators.csv",
    }.items():
        views = views.replace(key, path.as_posix())
    con.execute(views)
    return con


def main() -> int:
    SQL_OUT.mkdir(parents=True, exist_ok=True)
    con = connect()
    for path in sorted(SQL_DIR.glob("*.sql")):
        if path.name == VIEWS_FILE:
            continue
        df = con.execute(path.read_text(encoding="utf-8")).df()
        out = SQL_OUT / (path.stem + ".csv")
        df.to_csv(out, index=False)
        print(f"{path.name}: {len(df):,} rows -> outputs/sql/{out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
