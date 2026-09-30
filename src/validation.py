"""Human validation of the LLM labels.

  build   Draw 150 LLM-labeled complaints and write validation/to_label.csv, pre-filled
          with the LLM label, for a person to confirm or correct.
  score   Read the labeled file and write agreement, Cohen's kappa, and precision and
          recall per theme to validation/validation_report.md.

How to label: for each row, read the narrative and fill `human_primary_theme` with the
theme key you think is right. Type `ok` to confirm the LLM label. Rows left blank are
treated as not reviewed and are left out of the score, so an unreviewed row can never
count as agreement. `human_sentiment` is optional and works the same way.

The 150 rows are drawn evenly across the themes the LLM predicted, so rare themes get
enough rows to estimate precision. Because that is not a random draw, overall agreement
is also reported reweighted to the real mix of predicted themes.

Known limit: the reviewer sees the LLM label, which can anchor their judgment and
inflate agreement. The `--blind` option writes a second file without the LLM columns
for anyone who wants an unanchored check.
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from config import OUTPUT_DIR, VALIDATION_DIR
from labels import LLM, sample_labels
from metrics import agreement_metrics
from taxonomy import SENTIMENT_KEYS, THEME_KEYS, THEME_LABELS, TaxonomyError, normalize_theme

TO_LABEL = VALIDATION_DIR / "to_label.csv"
TO_LABEL_BLIND = VALIDATION_DIR / "to_label_blind.csv"
DESIGN = VALIDATION_DIR / "validation_design.csv"
REPORT = VALIDATION_DIR / "validation_report.md"
METRICS_JSON = OUTPUT_DIR / "validation_metrics.json"
N_ROWS = 150
SEED = 150
CONFIRM_WORDS = {"ok", "y", "yes", "same", "agree", "correct"}
EXIT_NO_LLM_LABELS = 3


def draw_validation_set(labeled: pd.DataFrame, n: int = N_ROWS, seed: int = SEED) -> pd.DataFrame:
    """About n/10 rows per predicted theme; themes with fewer rows give what they have
    and the shortfall is spread across the remaining themes."""
    remaining, picked = n, []
    themes = sorted(labeled["primary_theme"].unique(), key=lambda t: (labeled["primary_theme"] == t).sum())
    for i, theme in enumerate(themes):  # smallest themes first, so leftovers roll forward
        pool = labeled[labeled["primary_theme"] == theme]
        quota = min(len(pool), round(remaining / (len(themes) - i)))
        picked.append(pool.sample(quota, random_state=seed))
        remaining -= quota
    return pd.concat(picked).sample(frac=1.0, random_state=seed).reset_index(drop=True)


def cmd_build(args) -> int:
    labeled, source = sample_labels()
    if source != LLM:
        print("There are no LLM labels yet, so there is nothing to pre-label. Run "
              "src/classify.py first. No validation file was written.")
        return EXIT_NO_LLM_LABELS
    if TO_LABEL.exists() and not args.force:
        done = pd.read_csv(TO_LABEL)["human_primary_theme"].notna().sum()
        print(f"{TO_LABEL} already exists with {done} reviewed rows. Use --force to replace it.")
        return 1

    vset = draw_validation_set(labeled)
    # Predicted-theme mix in all narratives (weighted), used to reweight overall agreement.
    population = labeled.groupby("primary_theme")["weight"].sum() / labeled["weight"].sum()
    design = pd.DataFrame({
        "theme": population.index,
        "population_share": population.values,
        "validation_rows": [int((vset["primary_theme"] == t).sum()) for t in population.index],
    })
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    design.to_csv(DESIGN, index=False)

    out = pd.DataFrame({
        "complaint_id": vset["complaint_id"],
        "issuer": vset["issuer"],
        "date_received": pd.to_datetime(vset["date_received"]).dt.date,
        "narrative": vset["narrative"],
        "llm_primary_theme": vset["primary_theme"],
        "llm_secondary_theme": vset["secondary_theme"],
        "llm_sentiment": vset["sentiment"],
        "llm_named_benefits": vset["named_benefits"].map(lambda b: "; ".join(b) if len(b) else ""),
        "llm_card_product": vset["card_product"],
        "human_primary_theme": "",
        "human_sentiment": "",
        "notes": "",
    })
    out.to_csv(TO_LABEL, index=False)
    print(f"wrote {TO_LABEL} ({len(out)} rows)")
    if args.blind:
        out.drop(columns=[c for c in out.columns if c.startswith("llm_")]).to_csv(TO_LABEL_BLIND, index=False)
        print(f"wrote {TO_LABEL_BLIND}")
    print("Allowed themes: " + ", ".join(THEME_KEYS))
    print("Allowed sentiments: " + ", ".join(SENTIMENT_KEYS))
    return 0


def resolve_human(value, llm_value: str, allowed: list[str]) -> str | None:
    """Turn a reviewer's entry into a label. Blank means not reviewed."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == "":
        return None
    text = str(value).strip().lower()
    if text in CONFIRM_WORDS:
        return llm_value
    try:
        key = normalize_theme(text) if allowed is THEME_KEYS else text.replace(" ", "_")
    except TaxonomyError:
        key = text
    if key not in allowed:
        raise ValueError(f"'{value}' is not one of: {', '.join(allowed)}")
    return key


def score(df: pd.DataFrame, design: pd.DataFrame | None = None) -> dict:
    df = df.copy()
    df["human"] = [resolve_human(h, l, THEME_KEYS)
                   for h, l in zip(df["human_primary_theme"], df["llm_primary_theme"])]
    reviewed = df[df["human"].notna()]
    if reviewed.empty:
        return {"rows": len(df), "reviewed": 0}
    out = {"rows": len(df), "reviewed": len(reviewed),
           **agreement_metrics(list(reviewed["human"]), list(reviewed["llm_primary_theme"]), THEME_KEYS)}

    # Agreement reweighted to the real mix of predicted themes. Within a predicted theme
    # the agreement rate is that theme's precision.
    if design is not None:
        weights = dict(zip(design["theme"], design["population_share"]))
        covered = {t: m["precision"] for t, m in out["per_class"].items()
                   if m["precision"] is not None and t in weights}
        total = sum(weights[t] for t in covered)
        out["agreement_reweighted"] = sum(weights[t] * p for t, p in covered.items()) / total if total else None
        out["reweighting_covers_share"] = total

    out["confusion"] = (pd.crosstab(reviewed["human"], reviewed["llm_primary_theme"])
                        .reindex(index=THEME_KEYS, columns=THEME_KEYS, fill_value=0).to_dict())

    df["human_s"] = [resolve_human(h, l, SENTIMENT_KEYS)
                     for h, l in zip(df["human_sentiment"], df["llm_sentiment"])]
    s = df[df["human_s"].notna()]
    out["sentiment_reviewed"] = len(s)
    out["sentiment_agreement"] = float((s["human_s"] == s["llm_sentiment"]).mean()) if len(s) else None
    return out


def pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def write_report(m: dict) -> None:
    lines = [
        "# Validation report",
        "",
        "Generated by `src/validation.py score` from `validation/to_label.csv`.",
        "",
        f"- Rows in the validation set: {m['rows']}",
        f"- Rows reviewed by a person: {m['reviewed']}",
    ]
    if m["reviewed"] == 0:
        lines += ["", "No rows have been reviewed yet, so there are no results to report."]
    else:
        kappa = "n/a" if m["cohen_kappa"] is None else f"{m['cohen_kappa']:.3f}"
        lines += [
            f"- Agreement on primary theme: {pct(m['agreement'])}",
            f"- Agreement reweighted to the real mix of predicted themes: {pct(m.get('agreement_reweighted'))}",
            f"- Cohen's kappa: {kappa}",
            f"- Sentiment agreement: {pct(m['sentiment_agreement'])} on {m['sentiment_reviewed']} rows",
            "",
            "The human label is treated as the truth. Precision: of the rows the model gave this",
            "theme, the share the reviewer agreed with. Recall: of the rows the reviewer gave this",
            "theme, the share the model found.",
            "",
            "| Theme | Precision | Recall | F1 | Human rows | Model rows |",
            "|---|---|---|---|---|---|",
        ]
        for theme in THEME_KEYS:
            c = m["per_class"][theme]
            f1 = "n/a" if c["f1"] is None else f"{c['f1']:.2f}"
            lines.append(f"| {THEME_LABELS[theme]} | {pct(c['precision'])} | {pct(c['recall'])} | "
                         f"{f1} | {c['human_n']} | {c['model_n']} |")
        lines += [
            "",
            "Caveats: the reviewer saw the model's label while reviewing, which can inflate",
            "agreement. One reviewer labeled the set, so there is no measure of how much two",
            "people would disagree with each other. Per-theme figures rest on about 15 rows each.",
        ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_score(args) -> int:
    if not TO_LABEL.exists():
        print(f"{TO_LABEL} not found. Run `python src/validation.py build` after classification.")
        return 1
    df = pd.read_csv(TO_LABEL, dtype=str)
    design = pd.read_csv(DESIGN) if DESIGN.exists() else None
    try:
        m = score(df, design)
    except ValueError as exc:
        print(f"Could not score: {exc}")
        return 1
    METRICS_JSON.write_text(json.dumps(m, indent=2), encoding="utf-8")
    write_report(m)
    if m["reviewed"] == 0:
        print(f"0 of {m['rows']} rows reviewed. Fill in human_primary_theme and run again.")
    else:
        print(f"reviewed {m['reviewed']} of {m['rows']} | agreement {pct(m['agreement'])} | "
              f"kappa {m['cohen_kappa']:.3f} | report: {REPORT}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build")
    p.add_argument("--force", action="store_true", help="replace an existing to_label.csv")
    p.add_argument("--blind", action="store_true", help="also write a copy without the LLM columns")
    p.set_defaults(func=cmd_build)
    sub.add_parser("score").set_defaults(func=cmd_score)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
