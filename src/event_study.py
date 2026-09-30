"""Event study: fee, credit and benefit complaints before and after each card refresh.

For each event the treated issuer is compared with a pooled group of issuers that had
no premium card refresh in the window. The result is a difference in differences on
shares, plus a placebo range from pretending each comparison issuer was the treated one.

This is suggestive, not causal. Complaints are self-selected, the CFPB does not record
the card product, fee changes reached existing cardholders months after launch, and
other things changed in the same months (for example the Capital One and Discover
merger inside the comparison group).

Three lenses are reported because each has a different weakness:
  sub_issue   CFPB sub-issue codes on every complaint. Complete coverage, coarse meaning.
  mention     Keyword mentions in narratives. Precise wording, narratives only.
  theme       Theme model on every narrative. Closest to the question, model error applies.
"""
from __future__ import annotations

import sys

import pandas as pd

from config import CONTROL_ISSUERS, EVENT_WINDOWS_MONTHS, EVENTS, OUTPUT_DIR
from labels import SOURCE_DESCRIPTION, corpus_labels
from metrics import diff_in_diff, months_between
from taxonomy import MEMBERSHIP_VALUE_THEMES

SQL_OUT = OUTPUT_DIR / "sql"
SUMMARY_CSV = OUTPUT_DIR / "event_study_summary.csv"
MONTHLY_CSV = OUTPUT_DIR / "event_study_monthly.csv"


def load_panels() -> dict[str, tuple[pd.DataFrame, str]]:
    """metric key -> (monthly panel with columns issuer, month, k, n; description)."""
    sub = pd.read_csv(SQL_OUT / "07_value_issue_monthly.csv", parse_dates=["month"])
    men = pd.read_csv(SQL_OUT / "10_narrative_mentions_monthly.csv", parse_dates=["month"])
    themes, source = corpus_labels()
    themes["month"] = pd.to_datetime(themes["date_received"]).dt.to_period("M").dt.to_timestamp()
    themes["value"] = themes["primary_theme"].isin(MEMBERSHIP_VALUE_THEMES)
    themes["fee"] = themes["primary_theme"] == "annual_fee"
    th = themes.groupby(["issuer", "month"]).agg(
        n=("complaint_id", "size"), value=("value", "sum"), fee=("fee", "sum")).reset_index()

    def panel(df, k_col, n_col):
        return df.rename(columns={k_col: "k", n_col: "n"})[["issuer", "month", "k", "n"]]

    theme_note = f" [{SOURCE_DESCRIPTION[source]}]"
    return {
        "sub_issue:fees_rewards_promo": (
            panel(sub, "value_complaints", "complaints"),
            "Share of all complaints coded to a fee, rewards or promotional terms sub-issue"),
        "sub_issue:fees": (panel(sub, "fees", "complaints"),
                           "Share of all complaints coded 'Problem with fees'"),
        "sub_issue:rewards": (panel(sub, "rewards", "complaints"),
                              "Share of all complaints coded 'Problem with rewards from credit card'"),
        "mention:annual_fee": (panel(men, "mentions_annual_fee", "narratives"),
                               "Share of narratives that mention an annual or membership fee"),
        "mention:statement_credit": (panel(men, "mentions_statement_credit", "narratives"),
                                     "Share of narratives that mention a statement credit"),
        "theme:membership_value": (
            panel(th, "value", "n"),
            "Share of narratives with a fee, credit, rewards, travel benefit or protection theme" + theme_note),
        "theme:annual_fee": (panel(th, "fee", "n"),
                             "Share of narratives with the annual fee theme" + theme_note),
    }


def window_counts(panel: pd.DataFrame, issuers: list[str], event_month: pd.Timestamp,
                  months: int) -> tuple[int, int, int, int]:
    """(k_pre, n_pre, k_post, n_post) pooled over `issuers`. Post starts at the event month."""
    df = panel[panel["issuer"].isin(issuers)].copy()
    df["rel"] = df["month"].map(lambda m: months_between(m, event_month))
    pre = df[(df["rel"] >= -months) & (df["rel"] <= -1)]
    post = df[(df["rel"] >= 0) & (df["rel"] <= months - 1)]
    return int(pre["k"].sum()), int(pre["n"].sum()), int(post["k"].sum()), int(post["n"].sum())


def study(panel: pd.DataFrame, treated: str, controls: list[str], event_month: pd.Timestamp,
          months: int) -> dict:
    t = window_counts(panel, [treated], event_month, months)
    c = window_counts(panel, controls, event_month, months)
    res = diff_in_diff(t[0], t[1], t[2], t[3], c[0], c[1], c[2], c[3])
    # Placebo: pretend each comparison issuer had the event, against the remaining ones.
    placebo = []
    for fake in controls:
        rest = [x for x in controls if x != fake]
        ft = window_counts(panel, [fake], event_month, months)
        fc = window_counts(panel, rest, event_month, months)
        if min(ft[1], ft[3], fc[1], fc[3]) > 0:
            placebo.append(diff_in_diff(ft[0], ft[1], ft[2], ft[3], fc[0], fc[1], fc[2], fc[3]).did)
    post_months = panel[(panel["issuer"] == treated) & (panel["month"] >= event_month)]["month"].nunique()
    return {
        "treated_pre_pct": 100 * res.treated_pre, "treated_post_pct": 100 * res.treated_post,
        "control_pre_pct": 100 * res.control_pre, "control_post_pct": 100 * res.control_post,
        "treated_change_pts": 100 * res.treated_change, "control_change_pts": 100 * res.control_change,
        "did_pts": 100 * res.did, "did_ci_low_pts": 100 * res.ci_low, "did_ci_high_pts": 100 * res.ci_high,
        "n_treated_pre": res.n_treated_pre, "n_treated_post": res.n_treated_post,
        "n_control_pre": res.n_control_pre, "n_control_post": res.n_control_post,
        "placebo_did_min_pts": 100 * min(placebo) if placebo else None,
        "placebo_did_max_pts": 100 * max(placebo) if placebo else None,
        "outside_placebo_range": bool(placebo) and not (min(placebo) <= res.did <= max(placebo)),
        "post_months_observed": min(months, post_months),
    }


def monthly_series(panel: pd.DataFrame, treated: str, controls: list[str],
                   event_month: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for group, issuers in (("treated", [treated]), ("comparison", controls)):
        g = panel[panel["issuer"].isin(issuers)].groupby("month")[["k", "n"]].sum().reset_index()
        g["group"] = group
        g["rel_month"] = g["month"].map(lambda m: months_between(m, event_month))
        g["share_pct"] = 100 * g["k"] / g["n"]
        g["share_pct_3m"] = (100 * g["k"].rolling(3, min_periods=1).sum()
                             / g["n"].rolling(3, min_periods=1).sum())
        rows.append(g[(g["rel_month"] >= -18) & (g["rel_month"] <= 12)])
    return pd.concat(rows)


def product_mentions(event: dict) -> pd.DataFrame:
    """Narratives from the treated issuer that name the refreshed card, by month."""
    men = pd.read_csv(SQL_OUT / "10_narrative_mentions_monthly.csv", parse_dates=["month"])
    event_month = pd.Timestamp(event["event_month"])
    g = men[men["issuer"] == event["issuer"]].copy()
    g["k"] = g[event["product_mention_col"]]
    g["n"] = g["narratives"]
    g["group"] = "treated"
    g["rel_month"] = g["month"].map(lambda m: months_between(m, event_month))
    g["share_pct"] = 100 * g["k"] / g["n"]
    g["share_pct_3m"] = 100 * g["k"].rolling(3, min_periods=1).sum() / g["n"].rolling(3, min_periods=1).sum()
    return g[(g["rel_month"] >= -18) & (g["rel_month"] <= 12)][
        ["month", "k", "n", "group", "rel_month", "share_pct", "share_pct_3m"]]


def main() -> int:
    panels = load_panels()
    summary, monthly = [], []
    for event in EVENTS:
        event_month = pd.Timestamp(event["event_month"])
        for metric, (panel, description) in panels.items():
            lens, name = metric.split(":")
            for months in EVENT_WINDOWS_MONTHS:
                summary.append({
                    "event": event["key"], "treated_issuer": event["issuer"], "lens": lens,
                    "metric": name, "description": description, "window_months": months,
                    **study(panel, event["issuer"], CONTROL_ISSUERS, event_month, months),
                })
            monthly.append(monthly_series(panel, event["issuer"], CONTROL_ISSUERS, event_month)
                           .assign(event=event["key"], lens=lens, metric=name))
        monthly.append(product_mentions(event).assign(
            event=event["key"], lens="mention", metric="refreshed_card_named"))
        # The refreshed card named in a narrative: no comparison group exists, so report levels.
        pm = product_mentions(event)
        for months in EVENT_WINDOWS_MONTHS:
            pre = pm[(pm["rel_month"] >= -months) & (pm["rel_month"] <= -1)]
            post = pm[(pm["rel_month"] >= 0) & (pm["rel_month"] <= months - 1)]
            summary.append({
                "event": event["key"], "treated_issuer": event["issuer"], "lens": "mention",
                "metric": "refreshed_card_named",
                "description": f"Share of {event['issuer']} narratives that name {event['product_name']} "
                               "(no comparison group)",
                "window_months": months,
                "treated_pre_pct": 100 * pre["k"].sum() / pre["n"].sum(),
                "treated_post_pct": 100 * post["k"].sum() / post["n"].sum(),
                "treated_change_pts": 100 * (post["k"].sum() / post["n"].sum() - pre["k"].sum() / pre["n"].sum()),
                "n_treated_pre": int(pre["n"].sum()), "n_treated_post": int(post["n"].sum()),
                "k_treated_pre": int(pre["k"].sum()), "k_treated_post": int(post["k"].sum()),
                "post_months_observed": int(post["month"].nunique()),
            })

    summary_df = pd.DataFrame(summary).round(2)
    monthly_df = pd.concat(monthly)[
        ["event", "lens", "metric", "group", "month", "rel_month", "k", "n", "share_pct", "share_pct_3m"]
    ]
    numeric = monthly_df.select_dtypes("number").columns
    monthly_df[numeric] = monthly_df[numeric].round(2)
    summary_df.to_csv(SUMMARY_CSV, index=False)
    monthly_df.to_csv(MONTHLY_CSV, index=False)

    show = summary_df[summary_df["window_months"] == 6][
        ["event", "lens", "metric", "treated_pre_pct", "treated_post_pct", "control_pre_pct",
         "control_post_pct", "did_pts", "did_ci_low_pts", "did_ci_high_pts",
         "placebo_did_min_pts", "placebo_did_max_pts", "n_treated_pre", "n_treated_post"]]
    print(show.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
