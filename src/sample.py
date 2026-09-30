"""Draw the stratified sample of narratives that the LLM classifies.

Strata are issuer x quarter. Each stratum contributes a fixed number of narratives, or
all of them if it has fewer. American Express and Chase get larger cells because the
recommendations and the event study are about them, so that is where precision matters.
Every sampled row carries a weight (stratum size / rows sampled) so that results can be
weighted back to all narratives for that issuer.

The draw is deterministic: same data and same seed give the same sample.
"""
from __future__ import annotations

import sys

import duckdb
import pandas as pd

from config import COMPLAINTS_PARQUET, SAMPLE_IDS_CSV, SAMPLE_PARQUET
from metrics import allocate_stratified

SEED = 20260930
NARRATIVE_END = "2026-07-31"  # there are no narratives after July 2026
MIN_CHARS = 80  # shorter narratives rarely say what the problem is
PER_CELL = {"American Express": 80, "Chase": 60}
PER_CELL_DEFAULT = 32


def eligible(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        f"""
        SELECT complaint_id, issuer, date_received,
               strftime(date_received, '%Y') || '-Q' || quarter(date_received) AS quarter,
               issue, sub_issue, company_response, narrative
        FROM '{COMPLAINTS_PARQUET.as_posix()}'
        WHERE narrative IS NOT NULL
          AND length(narrative) >= {MIN_CHARS}
          AND date_received <= DATE '{NARRATIVE_END}'
        ORDER BY complaint_id
        """
    ).df()


def draw(pool: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    sizes = pool.groupby(["issuer", "quarter"]).size()
    parts = []
    for issuer, grp_sizes in sizes.groupby(level="issuer"):
        per_cell = PER_CELL.get(issuer, PER_CELL_DEFAULT)
        take = allocate_stratified(grp_sizes.droplevel("issuer").to_dict(), per_cell)
        for quarter, k in take.items():
            cell = pool[(pool["issuer"] == issuer) & (pool["quarter"] == quarter)]
            picked = cell.sample(n=k, random_state=seed)
            parts.append(picked.assign(stratum_size=len(cell), weight=len(cell) / k))
    return pd.concat(parts).sort_values("complaint_id").reset_index(drop=True)


def main() -> int:
    pool = eligible(duckdb.connect())
    sample = draw(pool)
    SAMPLE_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    sample.to_parquet(SAMPLE_PARQUET, index=False)
    SAMPLE_IDS_CSV.parent.mkdir(parents=True, exist_ok=True)
    sample[["complaint_id", "issuer", "quarter", "stratum_size", "weight"]].to_csv(
        SAMPLE_IDS_CSV, index=False)
    summary = sample.groupby("issuer").agg(
        sampled=("complaint_id", "size"), quarters=("quarter", "nunique"),
        narratives_represented=("weight", "sum"))
    print(f"eligible narratives: {len(pool):,} | sampled: {len(sample):,}")
    print(summary.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
