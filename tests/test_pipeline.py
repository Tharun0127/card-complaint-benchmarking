"""Sampling, validation scoring, event windows, fallback rules and quote selection."""
import pandas as pd
import pytest

from event_study import study, window_counts
from fallback import keyword_themes
from sample import draw
from themes import amex_vs_peers, pick_quote, theme_mix
from validation import draw_validation_set, resolve_human, score
from taxonomy import SENTIMENT_KEYS, THEME_KEYS


# --- sampling ---------------------------------------------------------------------------
def _pool():
    rows = []
    cid = 0
    for issuer, quarter, n in [("American Express", "2025-Q1", 200), ("American Express", "2025-Q2", 50),
                               ("Citi", "2025-Q1", 400), ("Citi", "2025-Q2", 10)]:
        for _ in range(n):
            cid += 1
            rows.append({"complaint_id": cid, "issuer": issuer, "quarter": quarter, "narrative": "x"})
    return pd.DataFrame(rows)


def test_stratified_draw_sizes_weights_and_determinism():
    sample = draw(_pool(), seed=1)
    sizes = sample.groupby(["issuer", "quarter"]).size().to_dict()
    assert sizes == {("American Express", "2025-Q1"): 80, ("American Express", "2025-Q2"): 50,
                     ("Citi", "2025-Q1"): 32, ("Citi", "2025-Q2"): 10}
    # weights add back to the number of narratives in each stratum
    back = sample.groupby(["issuer", "quarter"])["weight"].sum().to_dict()
    assert back[("American Express", "2025-Q1")] == pytest.approx(200)
    assert back[("Citi", "2025-Q1")] == pytest.approx(400)
    assert sample["complaint_id"].is_unique
    assert list(draw(_pool(), seed=1)["complaint_id"]) == list(sample["complaint_id"])


# --- theme shares -----------------------------------------------------------------------
def test_theme_mix_uses_weights_and_sums_to_100():
    df = pd.DataFrame({
        "issuer": ["American Express"] * 3 + ["Citi"] * 2,
        "primary_theme": ["annual_fee", "billing", "billing", "billing", "dispute_fraud"],
        "weight": [10.0, 5.0, 5.0, 1.0, 3.0],
    })
    mix = theme_mix(df).set_index(["issuer", "theme"])
    assert mix.loc[("American Express", "annual_fee"), "share_pct"] == pytest.approx(50.0)
    assert mix.loc[("Citi", "dispute_fraud"), "share_pct"] == pytest.approx(75.0)
    assert mix.groupby("issuer")["share_pct"].sum().tolist() == pytest.approx([100.0, 100.0])
    peers = amex_vs_peers(df).set_index("theme")
    assert peers.loc["annual_fee", "diff_pts"] == pytest.approx(50.0)
    assert peers.loc["billing", "index_vs_peers"] == pytest.approx(0.5 / 0.25)


# --- event study ------------------------------------------------------------------------
def _panel():
    months = pd.date_range("2025-03-01", "2025-08-01", freq="MS")  # event month = 2025-06
    rows = []
    for m in months:
        post = m >= pd.Timestamp("2025-06-01")
        rows.append({"issuer": "T", "month": m, "k": 30 if post else 10, "n": 100})
        rows.append({"issuer": "C1", "month": m, "k": 12 if post else 10, "n": 100})
        rows.append({"issuer": "C2", "month": m, "k": 12 if post else 10, "n": 100})
    return pd.DataFrame(rows)


def test_window_counts_put_the_event_month_in_the_post_period():
    k_pre, n_pre, k_post, n_post = window_counts(_panel(), ["T"], pd.Timestamp("2025-06-01"), 3)
    assert (k_pre, n_pre, k_post, n_post) == (30, 300, 90, 300)
    # a 2-month window uses only the two months on each side
    assert window_counts(_panel(), ["T"], pd.Timestamp("2025-06-01"), 2) == (20, 200, 60, 200)


def test_study_reports_did_in_points_and_a_placebo_range():
    out = study(_panel(), "T", ["C1", "C2"], pd.Timestamp("2025-06-01"), 3)
    assert out["treated_change_pts"] == pytest.approx(20.0)
    assert out["control_change_pts"] == pytest.approx(2.0)
    assert out["did_pts"] == pytest.approx(18.0)
    # the two comparison issuers moved together, so each placebo difference is zero
    assert out["placebo_did_min_pts"] == pytest.approx(0.0)
    assert out["placebo_did_max_pts"] == pytest.approx(0.0)
    assert out["outside_placebo_range"] is True


# --- validation -------------------------------------------------------------------------
def test_validation_draw_is_spread_across_predicted_themes():
    labeled = pd.DataFrame({
        "complaint_id": range(1000),
        "primary_theme": ["dispute_fraud"] * 600 + ["billing"] * 300 + ["annual_fee"] * 96 + ["lounge_travel_benefit"] * 4,
    })
    vset = draw_validation_set(labeled, n=40, seed=3)
    counts = vset["primary_theme"].value_counts().to_dict()
    assert len(vset) == 40 and vset["complaint_id"].is_unique
    assert counts["lounge_travel_benefit"] == 4  # a rare theme gives everything it has
    assert counts["annual_fee"] == counts["billing"] == counts["dispute_fraud"] == 12


def test_resolve_human_blank_confirm_and_correction():
    assert resolve_human("", "billing", THEME_KEYS) is None
    assert resolve_human(float("nan"), "billing", THEME_KEYS) is None
    assert resolve_human(" OK ", "billing", THEME_KEYS) == "billing"
    assert resolve_human("Annual fee", "billing", THEME_KEYS) == "annual_fee"
    assert resolve_human("very negative", "negative", SENTIMENT_KEYS) == "very_negative"
    with pytest.raises(ValueError):
        resolve_human("fees", "billing", THEME_KEYS)


def test_score_ignores_unreviewed_rows_and_reweights():
    df = pd.DataFrame({
        "llm_primary_theme": ["annual_fee", "annual_fee", "billing", "billing", "billing", "billing"],
        "human_primary_theme": ["ok", "billing", "ok", "ok", "", None],
        "llm_sentiment": ["negative"] * 6,
        "human_sentiment": ["ok", "very_negative", "", "", "", ""],
    })
    design = pd.DataFrame({"theme": ["annual_fee", "billing"], "population_share": [0.1, 0.9]})
    m = score(df, design)
    assert (m["rows"], m["reviewed"]) == (6, 4)
    assert m["agreement"] == pytest.approx(0.75)
    assert m["per_class"]["annual_fee"]["precision"] == pytest.approx(0.5)
    assert m["per_class"]["billing"]["recall"] == pytest.approx(2 / 3)
    # precision 0.5 on a theme that is 10% of predictions, 1.0 on one that is 90%
    assert m["agreement_reweighted"] == pytest.approx(0.1 * 0.5 + 0.9 * 1.0)
    assert m["sentiment_reviewed"] == 2 and m["sentiment_agreement"] == pytest.approx(0.5)
    assert score(df.assign(human_primary_theme=""), design) == {"rows": 6, "reviewed": 0}


# --- fallback rules and quotes ----------------------------------------------------------
@pytest.mark.parametrize("text, theme", [
    ("They raised my annual fee without notice", "annual_fee"),
    ("The airline credit never posted", "statement_credit_benefit"),
    ("I was denied entry to the Centurion lounge", "lounge_travel_benefit"),
    ("My trip delay claim was rejected", "insurance_protection_claim"),
    ("There is an unauthorized charge on my card", "dispute_fraud"),
])
def test_keyword_rules_fire_on_clear_cases(text, theme):
    assert keyword_themes(text) == [theme]


def test_keyword_rules_return_nothing_for_unrelated_text():
    assert keyword_themes("The weather was pleasant on Tuesday") == []


def test_pick_quote_is_short_on_theme_and_skips_heavy_redaction():
    narrative = ("On XX/XX/XXXX I called XXXX about XXXX. "
                 "They refused to refund the annual fee even though I cancelled within thirty days. "
                 "I am very upset.")
    quote = pick_quote(narrative, "annual_fee")
    assert quote == "They refused to refund the annual fee even though I cancelled within thirty days."
    assert pick_quote("Short. Tiny.", "annual_fee") is None
