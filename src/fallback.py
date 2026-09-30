"""TF-IDF + logistic regression theme model for every narrative.

It runs in one of two modes and always says which one it used.

  llm_distilled      LLM labels exist for the sample. The model is trained on them and
                     then labels all narratives, which gives dense monthly series for
                     the event study at no API cost. Cross-validated agreement with the
                     LLM labels is reported so the loss from distilling is visible.

  keyword_fallback   No LLM labels exist (no API key, or the API was unavailable).
                     Narratives that match the keyword rules of exactly one theme are
                     used as training seeds, and the model labels the rest. This is a
                     rough stand-in. It is NOT LLM classification and has not been
                     validated against human labels.

Output: data/processed/model_labels.parquet and outputs/model_label_report.json
"""
from __future__ import annotations

import json
import re
import sys

import duckdb
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline

from config import COMPLAINTS_PARQUET, MODEL_LABELS_PARQUET, OUTPUT_DIR
from labels import llm_sample_labels
from sample import MIN_CHARS, NARRATIVE_END
from taxonomy import THEME_KEYS

REPORT_JSON = OUTPUT_DIR / "model_label_report.json"
SEED = 7
MAX_SEEDS_PER_THEME = 6000
MIN_LLM_LABELS = 1000

# High-precision keyword rules, used only in keyword_fallback mode to pick training seeds.
KEYWORD_RULES: dict[str, str] = {
    "annual_fee": r"annual (membership )?fee|yearly fee|membership fee",
    "statement_credit_benefit": (
        r"statement credits?|uber (cash|credits?)|airline (fee |incidental )?credits?|hotel credits?|"
        r"dining credits?|resy|saks|entertainment credits?|walmart\+|clear (plus )?credit|"
        r"companion (certificate|pass|ticket|fare)|free night|travel credits?|dashpass"
    ),
    "rewards_points": (
        r"\b(points|miles)\b|cash ?back|rewards?\b|welcome (bonus|offer)|sign[- ]?up bonus|"
        r"bonus (offer|points|miles)|membership rewards|ultimate rewards|thank ?you points"
    ),
    "lounge_travel_benefit": (
        r"\blounges?\b|priority pass|centurion|global entry|tsa pre|travel portal|fine hotels|"
        r"concierge|(hotel|elite) status"
    ),
    "insurance_protection_claim": (
        r"purchase protection|trip (cancell?ation|delay|interruption)|"
        r"(rental car|car rental) (insurance|coverage|damage|loss)|extended warranty|"
        r"return protection|cell ?phone protection|baggage (insurance|delay)|"
        r"benefits? administrator|travel insurance|insurance claim"
    ),
    "dispute_fraud": (
        r"dispute|chargeback|fraud|unauthori[sz]ed|identity theft|stolen|scam|did not authorize"
    ),
    "customer_service": (
        r"customer service|representative|supervisor|on hold|hung up|rude|call(ed)? (me )?back"
    ),
    "credit_limit_account_closure": (
        r"credit (limit|line)|clos(ed|ing|ure) (of )?(my |the |our )?(account|card)|"
        r"account (was |has been |is )?(closed|suspended|restricted|cancell?ed)|financial review|"
        r"application (was |has been )?denied|denied (my|the) application"
    ),
    "billing": (
        r"late fees?|interest|\bapr\b|auto ?pay|minimum payment|balance transfer|"
        r"statement balance|credit (report|bureaus?)|collections?|payment (was|did|posted|not)"
    ),
}
_COMPILED = {theme: re.compile(pattern, re.IGNORECASE) for theme, pattern in KEYWORD_RULES.items()}


def keyword_themes(text: str) -> list[str]:
    """Themes whose keyword rule matches the text."""
    return [theme for theme, rx in _COMPILED.items() if rx.search(text)]


def load_narratives() -> pd.DataFrame:
    return duckdb.connect().execute(
        f"""
        SELECT complaint_id, issuer, date_received, narrative
        FROM '{COMPLAINTS_PARQUET.as_posix()}'
        WHERE narrative IS NOT NULL AND length(narrative) >= {MIN_CHARS}
          AND date_received <= DATE '{NARRATIVE_END}'
        ORDER BY complaint_id
        """
    ).df()


def make_model():
    return make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=150_000, sublinear_tf=True,
                        strip_accents="unicode", stop_words="english"),
        LogisticRegression(C=8.0, max_iter=2000, class_weight="balanced"),
    )


def keyword_seeds(corpus: pd.DataFrame, matches: pd.Series) -> pd.DataFrame:
    """Narratives that match the rules of exactly one theme, capped per theme."""
    single = matches.map(len) == 1
    seeds = corpus[single].assign(theme=matches[single].map(lambda m: m[0]))
    # Cap each theme so frequent themes do not swamp the rare ones.
    shuffled = seeds.sample(frac=1.0, random_state=SEED)
    return shuffled.groupby("theme").head(MAX_SEEDS_PER_THEME).reset_index(drop=True)


def main() -> int:
    corpus = load_narratives()
    llm = llm_sample_labels()
    report: dict = {"narratives_labeled": len(corpus)}

    if llm is not None and len(llm) >= MIN_LLM_LABELS:
        mode = "llm_distilled"
        train = llm.merge(corpus[["complaint_id", "narrative"]], on="complaint_id")
        x, y = train["narrative"], train["primary_theme"]
        # Cross-validated agreement with the LLM labels, on themes with enough rows to split.
        counts = y.value_counts()
        keep = y.isin(counts[counts >= 5].index)
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
        pred = cross_val_predict(make_model(), x[keep], y[keep], cv=cv)
        report.update({
            "training_rows": len(train),
            "cv_agreement_with_llm": round(float(accuracy_score(y[keep], pred)), 3),
            "cv_macro_f1_vs_llm": round(float(f1_score(y[keep], pred, average="macro")), 3),
            "cv_f1_by_theme": {
                theme: round(float(f), 3) for theme, f in zip(
                    sorted(y[keep].unique()),
                    f1_score(y[keep], pred, average=None, labels=sorted(y[keep].unique())))
            },
            "note": "Agreement is with LLM labels, not with human labels.",
        })
    else:
        mode = "keyword_fallback"
        matches = corpus["narrative"].map(keyword_themes)
        train = keyword_seeds(corpus, matches)
        n_no_match = int((matches.map(len) == 0).sum())
        x, y = train["narrative"], train["theme"]
        report.update({
            "training_rows": len(train),
            "seed_rows_by_theme": train["theme"].value_counts().to_dict(),
            "narratives_matching_no_rule": n_no_match,
            "note": "Keyword-seeded fallback. Not LLM classification. Not validated against human labels.",
        })

    model = make_model().fit(x, y)
    proba = model.predict_proba(corpus["narrative"])
    classes = model.classes_
    out = corpus[["complaint_id", "issuer", "date_received"]].copy()
    out["primary_theme"] = classes[proba.argmax(axis=1)]
    out["confidence"] = proba.max(axis=1)
    if mode == "keyword_fallback":
        # No rule matched and the model is unsure: call it "other" instead of forcing a theme.
        no_rule = (matches.map(len) == 0).to_numpy()
        out.loc[no_rule & (out["confidence"].to_numpy() < 0.5), "primary_theme"] = "other"
    out["label_source"] = mode
    assert set(out["primary_theme"]) <= set(THEME_KEYS)
    out.to_parquet(MODEL_LABELS_PARQUET, index=False)

    report["mode"] = mode
    report["theme_share_pct"] = (out["primary_theme"].value_counts(normalize=True) * 100).round(1).to_dict()
    REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
