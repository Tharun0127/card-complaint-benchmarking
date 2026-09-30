"""Theme tables and example quotes from the classified sample.

Shares are weighted back to all narratives for each issuer using the sampling weights.
Every output carries `label_source`, so LLM results and fallback results cannot be confused.
"""
from __future__ import annotations

import json
import re
import sys

import pandas as pd

from config import OUTPUT_DIR
from fallback import KEYWORD_RULES
from filters import ISSUERS
from labels import LLM, SOURCE_DESCRIPTION, sample_labels
from metrics import effective_sample_size, wilson_interval
from taxonomy import MEMBERSHIP_VALUE_THEMES, THEME_KEYS, THEME_LABELS

AMEX = "American Express"
MAX_QUOTES_PER_THEME = 3
QUOTE_MIN_CHARS, QUOTE_MAX_CHARS = 60, 230


def theme_mix(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for issuer, grp in df.groupby("issuer"):
        n_eff = effective_sample_size(grp["weight"])
        total = grp["weight"].sum()
        for theme in THEME_KEYS:
            hit = grp[grp["primary_theme"] == theme]
            p = hit["weight"].sum() / total
            low, high = wilson_interval(round(p * n_eff), round(n_eff))
            rows.append({"issuer": issuer, "theme": theme, "theme_label": THEME_LABELS[theme],
                         "sample_rows": len(hit), "issuer_sample_rows": len(grp),
                         "share_pct": 100 * p, "ci_low_pct": 100 * low, "ci_high_pct": 100 * high})
    return pd.DataFrame(rows)


def amex_vs_peers(df: pd.DataFrame) -> pd.DataFrame:
    """Amex theme share against the other six issuers pooled (weighted)."""
    amex, peers = df[df["issuer"] == AMEX], df[df["issuer"] != AMEX]
    rows = []
    for theme in THEME_KEYS:
        a = amex.loc[amex["primary_theme"] == theme, "weight"].sum() / amex["weight"].sum()
        p = peers.loc[peers["primary_theme"] == theme, "weight"].sum() / peers["weight"].sum()
        a_low, a_high = wilson_interval(round(a * effective_sample_size(amex["weight"])),
                                        round(effective_sample_size(amex["weight"])))
        rows.append({
            "theme": theme, "theme_label": THEME_LABELS[theme],
            "membership_value_theme": theme in MEMBERSHIP_VALUE_THEMES,
            "amex_share_pct": 100 * a, "amex_ci_low_pct": 100 * a_low, "amex_ci_high_pct": 100 * a_high,
            "peers_share_pct": 100 * p, "diff_pts": 100 * (a - p),
            "index_vs_peers": a / p if p > 0 else None,
            "amex_sample_rows": int((amex["primary_theme"] == theme).sum()),
            "peers_sample_rows": int((peers["primary_theme"] == theme).sum()),
        })
    return pd.DataFrame(rows).sort_values("diff_pts", ascending=False)


def relief_by_theme(df: pd.DataFrame) -> pd.DataFrame:
    """Share of complaints closed with monetary relief, by theme: Amex against peers."""
    closed = df[df["company_response"] != "In progress"].copy()
    closed["relief"] = closed["company_response"] == "Closed with monetary relief"
    closed["group"] = closed["issuer"].map(lambda i: "amex" if i == AMEX else "peers")
    rows = []
    for theme in THEME_KEYS:
        row = {"theme": theme, "theme_label": THEME_LABELS[theme]}
        for group in ("amex", "peers"):
            g = closed[(closed["group"] == group) & (closed["primary_theme"] == theme)]
            row[f"{group}_sample_rows"] = len(g)
            row[f"{group}_monetary_relief_pct"] = (
                100 * (g["weight"] * g["relief"]).sum() / g["weight"].sum() if len(g) else None)
        rows.append(row)
    return pd.DataFrame(rows)


def sentiment_by_theme(df: pd.DataFrame) -> pd.DataFrame:
    amex = df[df["issuer"] == AMEX]
    out = (amex.groupby(["primary_theme", "sentiment"])["weight"].sum()
           / amex.groupby("primary_theme")["weight"].sum()).rename("share").reset_index()
    out["share_pct"] = 100 * out.pop("share")
    out["theme_label"] = out["primary_theme"].map(THEME_LABELS)
    return out


def top_named(df: pd.DataFrame, column: str, top: int = 15) -> pd.DataFrame:
    """Most often named benefits or card products, for Amex and for peers."""
    values = df[["issuer", column]].explode(column).dropna()
    values[column] = values[column].astype(str).str.strip()
    values = values[values[column] != ""]
    values["group"] = values["issuer"].map(lambda i: AMEX if i == AMEX else "Other six issuers")
    counts = (values.assign(key=values[column].str.lower())
              .groupby(["group", "key"]).agg(mentions=("key", "size"), name=(column, "first"))
              .reset_index().sort_values(["group", "mentions"], ascending=[True, False]))
    return counts.groupby("group").head(top)[["group", "name", "mentions"]]


_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def pick_quote(narrative: str, theme: str) -> str | None:
    """A short sentence from the narrative that is on the theme, or None."""
    rule = KEYWORD_RULES.get(theme)
    for sentence in _SENTENCE.split(" ".join(narrative.split())):
        if not (QUOTE_MIN_CHARS <= len(sentence) <= QUOTE_MAX_CHARS):
            continue
        if sentence.count("XX") > 1 or "{$" in sentence:
            continue
        if rule is None or re.search(rule, sentence, re.IGNORECASE):
            return sentence
    return None


def example_quotes(df: pd.DataFrame) -> dict[str, list[dict]]:
    """Up to three short quotes per theme, Amex first, one per issuer where possible."""
    quotes: dict[str, list[dict]] = {}
    order = {issuer: i for i, issuer in enumerate(ISSUERS)}
    for theme in THEME_KEYS:
        if theme == "other":
            continue
        rows = df[df["primary_theme"] == theme].sort_values("complaint_id")
        rows = rows.assign(rank=rows["issuer"].map(order)).sort_values(["rank", "complaint_id"])
        picked, used_issuers = [], set()
        for allow_repeat in (False, True):
            for row in rows.itertuples():
                if len(picked) == MAX_QUOTES_PER_THEME:
                    break
                if (not allow_repeat and row.issuer in used_issuers) or any(
                        p["complaint_id"] == row.complaint_id for p in picked):
                    continue
                text = pick_quote(row.narrative, theme)
                if text:
                    picked.append({"complaint_id": int(row.complaint_id), "issuer": row.issuer,
                                   "quarter": row.quarter, "text": text})
                    used_issuers.add(row.issuer)
        quotes[theme] = picked
    return quotes


def main() -> int:
    df, source = sample_labels()
    note = SOURCE_DESCRIPTION[source]

    def save(frame: pd.DataFrame, name: str) -> None:
        frame.round(2).assign(label_source=source).to_csv(OUTPUT_DIR / name, index=False)

    save(theme_mix(df), "theme_mix_by_issuer.csv")
    save(amex_vs_peers(df), "theme_amex_vs_peers.csv")
    save(relief_by_theme(df), "theme_relief_amex_vs_peers.csv")
    optional = ["theme_sentiment_amex.csv", "named_benefits_top.csv", "card_products_top.csv"]
    if source == LLM:
        save(sentiment_by_theme(df), optional[0])
        save(top_named(df, "named_benefits"), optional[1])
        save(top_named(df, "card_product"), optional[2])
    else:
        # Sentiment, named benefits and card products come only from the LLM.
        for name in optional:
            (OUTPUT_DIR / name).unlink(missing_ok=True)

    quotes = {"label_source": source, "label_source_description": note, "quotes": example_quotes(df)}
    (OUTPUT_DIR / "example_quotes.json").write_text(json.dumps(quotes, indent=2, ensure_ascii=False),
                                                   encoding="utf-8")
    summary = {
        "label_source": source, "label_source_description": note, "sample_rows": len(df),
        "sample_rows_by_issuer": df["issuer"].value_counts().to_dict(),
        "narratives_represented": int(round(df["weight"].sum())),
    }
    (OUTPUT_DIR / "theme_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"label source: {note}")
    print(amex_vs_peers(df).round(1)[["theme_label", "amex_share_pct", "peers_share_pct", "diff_pts",
                                      "index_vs_peers", "amex_sample_rows"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
