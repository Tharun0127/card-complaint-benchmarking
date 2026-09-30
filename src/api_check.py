"""Cross-check the archive against the live CFPB complaint database API.

The archive is the source of record for this project. This script only answers three
questions and writes the answers to outputs/api_crosscheck.json:
  1. Does the live API still serve structured fields?
  2. Does it still serve narratives?
  3. Do archive counts by issuer and year match the API counts?
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

import duckdb

from config import COMPLAINTS_PARQUET, LIVE_API_URL, OUTPUT_DIR
from filters import COMPANY_TO_ISSUER

HEADERS = {"User-Agent": "card-complaint-benchmarking/1.0", "Accept": "application/json"}
OUT = OUTPUT_DIR / "api_crosscheck.json"
# 2023 is left out: until August 2023 credit cards sat under "Credit card or prepaid card",
# so a simple product filter on the API is not like for like with the archive filter.
YEARS = [2024, 2025]


def query(**params) -> dict:
    url = LIVE_API_URL + "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def total(result: dict) -> int:
    return int(result["hits"]["total"]["value"])


def main() -> int:
    out: dict = {"api_url": LIVE_API_URL}
    try:
        latest = query(size=1, sort="created_date_desc", product="Credit card", no_aggs="true")
    except Exception as exc:  # network or HTTP failure: record it and carry on with the archive
        out["api_available"] = False
        out["error"] = f"{type(exc).__name__}: {exc}"
        OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(json.dumps(out, indent=2))
        return 0

    hit = latest["hits"]["hits"][0]["_source"]
    out["api_available"] = True
    out["fields_served"] = sorted(hit.keys())
    out["latest_credit_card_complaint_received"] = hit.get("date_received", "")[:10]
    out["narrative_field_present"] = "complaint_what_happened" in hit
    out["complaints_flagged_has_narrative"] = total(query(size=0, has_narrative="true", no_aggs="true"))
    out["credit_card_complaints_received_after_2026_08_14"] = total(
        query(size=0, product="Credit card", date_received_min="2026-08-15", no_aggs="true")
    )

    con = duckdb.connect()
    rows = []
    for company, issuer in COMPANY_TO_ISSUER.items():
        for year in YEARS:
            api_n = total(query(
                size=0, company=company, product="Credit card", no_aggs="true",
                date_received_min=f"{year}-01-01", date_received_max=f"{year + 1}-01-01",
            ))
            archive_n, = con.execute(
                f"""SELECT count(*) FROM '{COMPLAINTS_PARQUET.as_posix()}'
                    WHERE issuer = ? AND year(date_received) = ?""", [issuer, year]
            ).fetchone()
            rows.append({"issuer": issuer, "year": year, "archive": archive_n, "live_api": api_n,
                         "archive_as_pct_of_api": round(100 * archive_n / api_n, 1) if api_n else None})
    out["counts_by_issuer_year"] = rows
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
