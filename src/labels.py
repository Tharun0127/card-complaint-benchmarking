"""One place that decides which theme labels the analysis uses, and says so.

Every downstream table and chart carries a `label_source` so a reader can always tell
whether a number comes from the LLM or from the fallback model.
"""
from __future__ import annotations

import os

import pandas as pd

from config import LABELS_JSONL, MODEL_LABELS_PARQUET, SAMPLE_PARQUET
from prompts import PROMPT_VERSION

LLM = "llm"
LLM_DISTILLED = "llm_distilled"
KEYWORD_FALLBACK = "keyword_fallback"

SOURCE_DESCRIPTION = {
    LLM: "LLM classification (Anthropic API) of the stratified sample",
    LLM_DISTILLED: "TF-IDF + logistic regression trained on the LLM labels, applied to all narratives",
    KEYWORD_FALLBACK: (
        "FALLBACK: keyword-seeded TF-IDF + logistic regression. Not LLM classification and "
        "not validated against human labels"
    ),
}

# The sample counts as LLM-labeled once this share of it has a valid label.
MIN_LLM_COVERAGE = 0.9


def llm_sample_labels() -> pd.DataFrame | None:
    """Valid LLM labels for sampled complaints, or None if there are none.

    If more than one model has labeled the sample, CLASSIFY_MODEL picks one, otherwise
    the model with the most valid labels is used.
    """
    if not LABELS_JSONL.exists() or LABELS_JSONL.stat().st_size == 0:
        return None
    cache = pd.read_json(LABELS_JSONL, lines=True, dtype={"complaint_id": "int64"})
    ok = cache[(cache["status"] == "ok") & (cache["prompt_version"] == PROMPT_VERSION)]
    if ok.empty:
        return None
    wanted = os.environ.get("CLASSIFY_MODEL")
    model = wanted if wanted in set(ok["model"]) else ok["model"].value_counts().idxmax()
    ok = ok[ok["model"] == model].drop_duplicates("complaint_id", keep="last")
    cols = ["complaint_id", "model", "primary_theme", "secondary_theme", "sentiment",
            "named_benefits", "card_product", "narrative_truncated"]
    return ok[cols].reset_index(drop=True)


def sample_labels() -> tuple[pd.DataFrame, str]:
    """The stratified sample with a theme per row, and the source of those themes."""
    sample = pd.read_parquet(SAMPLE_PARQUET)
    llm = llm_sample_labels()
    if llm is not None and len(llm) >= MIN_LLM_COVERAGE * len(sample):
        out = sample.merge(llm, on="complaint_id", how="inner")
        # Reweight within each stratum so rows without a valid label do not shrink it.
        labeled = out.groupby(["issuer", "quarter"])["complaint_id"].transform("size")
        out["weight"] = out["stratum_size"] / labeled
        return out.assign(label_source=LLM), LLM

    model = pd.read_parquet(MODEL_LABELS_PARQUET)[["complaint_id", "primary_theme", "label_source"]]
    out = sample.merge(model, on="complaint_id", how="inner")
    for col in ("secondary_theme", "sentiment", "named_benefits", "card_product"):
        out[col] = None
    return out, str(out["label_source"].iloc[0])


def corpus_labels() -> tuple[pd.DataFrame, str]:
    """Model labels for every narrative, and their source."""
    out = pd.read_parquet(MODEL_LABELS_PARQUET)
    return out, str(out["label_source"].iloc[0])
