"""Turn the downloaded archive zips into two parquet files.

cards_all.parquet   every credit card complaint received on or after START_DATE, all companies
complaints.parquet  the same rows restricted to the seven issuers, with an `issuer` column

Each zip is processed on its own and cached as a parquet part, so a rerun only touches
files that have not been processed yet.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import duckdb

from config import ARCHIVE_FILES, COMPLAINTS_PARQUET, PROCESSED_DIR, RAW_DIR, START_DATE
from filters import card_filter_sql, issuer_case_sql

PARTS_DIR = PROCESSED_DIR / "parts"
CARDS_ALL_PARQUET = PROCESSED_DIR / "cards_all.parquet"
ROW_COUNTS_CSV = PROCESSED_DIR / "archive_row_counts.csv"

# Archive column name -> column name used in this project.
COLUMNS = {
    "Date received": "date_received",
    "Product": "product",
    "Sub-product": "sub_product",
    "Issue": "issue",
    "Sub-issue": "sub_issue",
    "Consumer complaint narrative": "narrative",
    "Company public response": "company_public_response",
    "Company": "company",
    "State": "state",
    "ZIP code": "zip_code",
    "Tags": "tags",
    "Submitted via": "submitted_via",
    "Date sent to company": "date_sent_to_company",
    "Company response to consumer": "company_response",
    "Timely response?": "timely_response",
    "Complaint ID": "complaint_id",
}


def _posix(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def process_zip(zip_path: Path, con: duckdb.DuckDBPyConnection) -> Path:
    part = PARTS_DIR / (zip_path.stem + ".parquet")
    counts = PARTS_DIR / (zip_path.stem + ".counts.csv")
    if part.exists() and counts.exists():
        print(f"skip  {zip_path.name}")
        return part

    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"{zip_path.name}: expected one CSV, found {members}")
        csv_path = Path(zf.extract(members[0], RAW_DIR / "_tmp"))

    try:
        select_cols = ",\n            ".join(f'"{src}" AS {dst}' for src, dst in COLUMNS.items())
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE raw AS
            SELECT {select_cols}
            FROM read_csv('{_posix(csv_path)}', header = true, all_varchar = true,
                          quote = '"', escape = '"', max_line_size = 20000000)
            """
        )
        # A misparsed multi-line narrative would show up as a non-numeric id or a bad date.
        bad = con.execute(
            """
            SELECT count(*) FROM raw
            WHERE NOT regexp_full_match(complaint_id, '\\d+')
               OR try_cast(date_received AS DATE) IS NULL
            """
        ).fetchone()[0]
        if bad:
            raise ValueError(f"{zip_path.name}: {bad} rows failed the id/date sanity check")

        con.execute(
            f"""
            COPY (
                SELECT '{zip_path.name}' AS source_file,
                       count(*) AS rows_total,
                       count(*) FILTER (WHERE {card_filter_sql()}) AS rows_card,
                       min(date_received) AS min_date_received,
                       max(date_received) AS max_date_received
                FROM raw
            ) TO '{_posix(counts)}' (HEADER, DELIMITER ',')
            """
        )
        con.execute(
            f"""
            COPY (
                SELECT CAST(complaint_id AS BIGINT) AS complaint_id,
                       CAST(date_received AS DATE) AS date_received,
                       try_cast(date_sent_to_company AS DATE) AS date_sent_to_company,
                       product, sub_product, issue, sub_issue,
                       nullif(trim(narrative), '') AS narrative,
                       company_public_response, trim(company) AS company, state, zip_code,
                       tags, submitted_via, company_response, timely_response,
                       '{zip_path.name}' AS source_file
                FROM raw
                WHERE {card_filter_sql()}
                  AND CAST(date_received AS DATE) >= DATE '{START_DATE}'
            ) TO '{_posix(part)}' (FORMAT parquet)
            """
        )
    finally:
        csv_path.unlink(missing_ok=True)
    n = con.execute(f"SELECT count(*) FROM '{_posix(part)}'").fetchone()[0]
    print(f"done  {zip_path.name}: {n:,} card complaints")
    return part


def combine(con: duckdb.DuckDBPyConnection) -> None:
    parts_glob = _posix(PARTS_DIR / "*.parquet")
    # The same complaint can appear in two exports. Keep the row from the later export.
    con.execute(
        f"""
        COPY (
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY complaint_id
                    ORDER BY try_cast(regexp_extract(source_file, 'Export_(\\d+)_', 1) AS INT) DESC
                ) AS rn
                FROM read_parquet('{parts_glob}')
            ) WHERE rn = 1
            ORDER BY date_received, complaint_id
        ) TO '{_posix(CARDS_ALL_PARQUET)}' (FORMAT parquet)
        """
    )
    con.execute(
        f"""
        COPY (
            SELECT {issuer_case_sql()} AS issuer, *
            FROM '{_posix(CARDS_ALL_PARQUET)}'
            WHERE {issuer_case_sql()} IS NOT NULL
        ) TO '{_posix(COMPLAINTS_PARQUET)}' (FORMAT parquet)
        """
    )
    con.execute(
        f"""
        COPY (SELECT * FROM read_csv('{_posix(PARTS_DIR / "*.counts.csv")}', header = true)
              ORDER BY min_date_received)
        TO '{_posix(ROW_COUNTS_CSV)}' (HEADER, DELIMITER ',')
        """
    )
    all_n, = con.execute(f"SELECT count(*) FROM '{_posix(CARDS_ALL_PARQUET)}'").fetchone()
    iss_n, = con.execute(f"SELECT count(*) FROM '{_posix(COMPLAINTS_PARQUET)}'").fetchone()
    print(f"cards_all.parquet: {all_n:,} rows | complaints.parquet (7 issuers): {iss_n:,} rows")


def main() -> int:
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    missing = [name for name in ARCHIVE_FILES if not (RAW_DIR / name).exists()]
    if missing:
        print("Missing archive files, run src/download.py first:\n  " + "\n  ".join(missing))
        return 1
    for name in ARCHIVE_FILES:
        process_zip(RAW_DIR / name, con)
    combine(con)
    return 0


if __name__ == "__main__":
    sys.exit(main())
