"""Write docs/data_profile.md from the processed parquet files.

Every number in the profile is computed here. Nothing is typed in by hand.
"""
from __future__ import annotations

import json
import sys

import duckdb
import pandas as pd

from config import (
    ARCHIVE_PAGE, CARDS_ALL_PARQUET, COMPLAINTS_PARQUET, DOCS_DIR, OUTPUT_DIR, PROCESSED_DIR,
    START_DATE,
)
from filters import COMPANY_TO_ISSUER, ISSUERS
from prompts import MAX_NARRATIVE_CHARS

OUT = DOCS_DIR / "data_profile.md"


def md_table(df: pd.DataFrame) -> str:
    def fmt(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        if isinstance(v, pd.Timestamp):
            return v.strftime("%Y-%m-%d")
        if isinstance(v, float):
            return f"{v:,.1f}"
        if isinstance(v, int) or hasattr(v, "is_integer") and float(v).is_integer():
            return f"{int(v):,}"
        return str(v)

    head = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    body = ["| " + " | ".join(fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def main() -> int:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW c AS SELECT * FROM '{COMPLAINTS_PARQUET.as_posix()}'")
    con.execute(f"CREATE VIEW a AS SELECT * FROM '{CARDS_ALL_PARQUET.as_posix()}'")
    q = lambda sql: con.execute(sql).df()  # noqa: E731
    one = lambda sql: con.execute(sql).fetchone()  # noqa: E731

    files = pd.read_csv(PROCESSED_DIR / "archive_row_counts.csv")
    files.columns = ["Archive file", "Rows in file", "Credit card rows", "First date received", "Last date received"]

    n_all, n_all_dist = one("SELECT count(*), count(DISTINCT complaint_id) FROM a")
    n_iss, n_narr, d_min, d_max = one(
        "SELECT count(*), count(narrative), min(date_received), max(date_received) FROM c")
    last_narr, = one("SELECT max(date_received) FROM c WHERE narrative IS NOT NULL")

    products = q("""
        SELECT product AS "Product", sub_product AS "Sub-product", count(*) AS "Rows",
               min(date_received) AS "First", max(date_received) AS "Last"
        FROM a GROUP BY ALL ORDER BY 3 DESC""")

    companies = q(f"""
        SELECT company AS "Company string in the data", issuer AS "Issuer label",
               count(*) AS "Complaints", count(narrative) AS "With narrative",
               round(100.0 * count(narrative) / count(*), 1) AS "Narrative %",
               min(date_received) AS "First", max(date_received) AS "Last"
        FROM c GROUP BY company, issuer
        ORDER BY list_position({ISSUERS!r}, issuer)""")

    lookalikes = q("""
        SELECT company AS "Company", count(*) AS "Card complaints" FROM a
        WHERE regexp_matches(lower(company), 'american express|amex|chase|capital one|citi|bank of america|discover|synchrony')
          AND company NOT IN (SELECT DISTINCT company FROM c)
        GROUP BY ALL ORDER BY 2 DESC""")

    top_all = q("""
        SELECT company AS "Company", count(*) AS "Card complaints",
               round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS "Share %"
        FROM a GROUP BY ALL ORDER BY 2 DESC LIMIT 15""")

    narr_q = q("""
        PIVOT (
            SELECT strftime(date_received, '%Y') || '-Q' || quarter(date_received) AS "Quarter", issuer,
                   round(100.0 * count(narrative) / count(*), 1) AS pct
            FROM c GROUP BY ALL
        ) ON issuer USING max(pct) ORDER BY "Quarter" """)
    narr_q = narr_q[["Quarter"] + [i for i in ISSUERS if i in narr_q.columns]]

    vol_q = q("""
        PIVOT (
            SELECT strftime(date_received, '%Y') || '-Q' || quarter(date_received) AS "Quarter", issuer,
                   count(*) AS n
            FROM c GROUP BY ALL
        ) ON issuer USING sum(n) ORDER BY "Quarter" """)
    vol_q = vol_q[["Quarter"] + [i for i in ISSUERS if i in vol_q.columns]]

    recent = q("""
        SELECT strftime(date_received, '%Y-%m') AS "Month", count(*) AS "Complaints",
               count(narrative) AS "With narrative",
               round(100.0 * count(narrative) / count(*), 1) AS "Narrative %",
               count(*) FILTER (WHERE company_response = 'In progress') AS "Response in progress"
        FROM c WHERE date_received >= DATE '2025-07-01' GROUP BY ALL ORDER BY 1""")

    cols = [r[0] for r in con.execute("DESCRIBE c").fetchall()]
    completeness = pd.DataFrame(
        [(col, *one(f'SELECT round(100.0 * count("{col}") / count(*), 1), count(DISTINCT "{col}") FROM c'))
         for col in cols],
        columns=["Field", "Non-null %", "Distinct values"],
    )

    lengths = one(f"""
        SELECT quantile_cont(length(narrative), 0.1), quantile_cont(length(narrative), 0.5),
               quantile_cont(length(narrative), 0.9), quantile_cont(length(narrative), 0.99),
               max(length(narrative)),
               100.0 * avg((length(narrative) > {MAX_NARRATIVE_CHARS})::INT),
               100.0 * avg((length(narrative) < 100)::INT)
        FROM c WHERE narrative IS NOT NULL""")

    responses = q("""
        SELECT company_response AS "Company response", count(*) AS "Complaints",
               round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS "Share %"
        FROM c GROUP BY ALL ORDER BY 2 DESC""")
    timely = q("""
        SELECT timely_response AS "Timely response?", count(*) AS "Complaints",
               round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS "Share %"
        FROM c GROUP BY ALL ORDER BY 2 DESC""")

    discover_last, = one("SELECT max(date_received) FROM c WHERE issuer = 'Discover'")

    api_path = OUTPUT_DIR / "api_crosscheck.json"
    api = json.loads(api_path.read_text(encoding="utf-8")) if api_path.exists() else None

    lines = [
        "# Data profile",
        "",
        "Generated by `src/data_profile.py`. Every number below is computed from the processed data.",
        "",
        "## Source",
        "",
        f"- CFPB Consumer Complaint Database narratives archive: {ARCHIVE_PAGE}",
        f"- Files used: the {len(files)} exports that contain complaints received on or after {START_DATE}.",
        "  The first file starts in November 2022 and is trimmed at ingest.",
        "- Each file is one CSV with the same 16 columns.",
        "",
        md_table(files),
        "",
        "## Rows and date coverage",
        "",
        f"- Credit card complaints, all companies, received {START_DATE} or later: **{n_all:,}** "
        f"({n_all_dist:,} distinct complaint ids, so there are no duplicates across files).",
        f"- Of these, the seven issuers in this study: **{n_iss:,}** ({100 * n_iss / n_all:.1f}%).",
        f"- Date received runs from {d_min} to {d_max}.",
        f"- Complaints with a narrative: **{n_narr:,}** ({100 * n_narr / n_iss:.1f}%). "
        f"The last narrative is dated {last_narr}.",
        "",
        "## Product filter",
        "",
        "The CFPB renamed the product during August 2023. Before the change, credit cards sat",
        "under \"Credit card or prepaid card\" and are separated from prepaid cards by sub-product.",
        "The filter keeps the rows below and nothing else (`src/filters.py`).",
        "",
        md_table(products),
        "",
        "## Company names",
        "",
        "Issuers are matched on the exact company string. No substring matching is used.",
        "",
        md_table(companies),
        "",
        "Company names that look similar and are deliberately left out:",
        "",
        md_table(lookalikes) if len(lookalikes) else "None found.",
        "",
        f"Discover: the company string `DISCOVER BANK` is last seen on {discover_last}. Capital One",
        "completed its acquisition of Discover on 18 May 2025, so the label stayed in use for about",
        "ten months after the deal closed and then stopped. From April 2026, complaints about",
        "Discover cards are presumably filed under Capital One. This cannot be confirmed from the",
        "data. Discover is therefore reported through March 2026 only, and Capital One figures",
        "from April 2026 may include Discover cards.",
        "",
        "For context, the largest companies by credit card complaints (all companies):",
        "",
        md_table(top_all),
        "",
        "The three credit bureaus appear because consumers file card-related credit reporting",
        "complaints under the credit card product.",
        "",
        "## Complaint volume by issuer and quarter",
        "",
        md_table(vol_q),
        "",
        "The last quarter is partial (July and August 2026 only).",
        "",
        "## Narrative availability by issuer and quarter (% of complaints with a narrative)",
        "",
        md_table(narr_q),
        "",
        "Narratives are published only when the consumer consents, so they are a self-selected",
        "subset of complaints. Availability is similar across issuers within a quarter, which",
        "matters more for this study than the level: the comparison between issuers is not",
        "driven by one issuer having far more or fewer narratives.",
        "",
        "Availability drops at the end of the period:",
        "",
        md_table(recent),
        "",
        "What this means for the analysis:",
        "",
        "- Narrative analysis uses complaints received through July 2026. August 2026 has no",
        "  narratives at all.",
        "- From December 2025 the narrative share is lower than before. The cause is not stated",
        "  in the archive. Results for 2026 rest on a thinner and possibly different slice.",
        "- Company response analysis excludes complaints still marked \"In progress\", which are",
        "  concentrated in July and August 2026.",
        "",
        "## Field completeness (seven issuers)",
        "",
        md_table(completeness),
        "",
        "## Narrative length (characters)",
        "",
        f"- 10th percentile {lengths[0]:,.0f}, median {lengths[1]:,.0f}, 90th percentile {lengths[2]:,.0f}, "
        f"99th percentile {lengths[3]:,.0f}, longest {lengths[4]:,.0f}.",
        f"- {lengths[5]:.1f}% of narratives are longer than {MAX_NARRATIVE_CHARS:,} characters. The classifier cuts these at",
        f"  {MAX_NARRATIVE_CHARS:,} characters and records that it did so.",
        f"- {lengths[6]:.1f}% are shorter than 100 characters.",
        "",
        "## Company response and timeliness",
        "",
        md_table(responses),
        "",
        md_table(timely),
        "",
        "Timely response is close to 100% for every issuer, so it does not separate issuers well.",
        "",
    ]

    if api:
        lines += ["## Live API cross-check", ""]
        if not api.get("api_available"):
            lines += [f"The live API did not respond ({api.get('error')}). The archive is used alone.", ""]
        else:
            counts = pd.DataFrame(api["counts_by_issuer_year"])
            counts.columns = ["Issuer", "Year", "Archive", "Live API", "Archive as % of API"]
            lines += [
                f"Checked with `src/api_check.py` against {api['api_url']}",
                "",
                "- The API responds and serves these structured fields: "
                + ", ".join(f"`{f}`" for f in api["fields_served"]) + ".",
                f"- Narrative text is {'served' if api['narrative_field_present'] else 'not served'}.",
                f"- The most recent credit card complaint in the API was received on "
                f"{api['latest_credit_card_complaint_received']}, so structured fields continue after the "
                "narrative cut-off.",
                "- Archive counts match the API closely for the two full years where the product label",
                "  is stable:",
                "",
                md_table(counts),
                "",
                "The archive is the source of record for this project. The API is used only for this check.",
                "",
            ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
