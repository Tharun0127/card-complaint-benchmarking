"""Collect every headline number into outputs/findings.json.

The dashboard, memo, README and resume bullets read their numbers from this file, so a
number is computed once and cannot drift between documents.
"""
from __future__ import annotations

import json
import sys

import pandas as pd

from config import OUTPUT_DIR, VALIDATION_DIR
from costing import DEFAULT_BUDGET_USD, PRICES
from labels import KEYWORD_FALLBACK, LLM, SOURCE_DESCRIPTION, llm_sample_labels
from run_sql import connect

SQL_OUT = OUTPUT_DIR / "sql"
FINDINGS_JSON = OUTPUT_DIR / "findings.json"
AMEX = "American Express"
SUB_PROMO = "Didn't receive advertised or promotional terms"
SUB_REWARDS = "Problem with rewards from credit card"
SUB_FEES = "Problem with fees"
SUB_LIMIT = "Credit card company won't increase or decrease your credit limit"
SUB_DENIED = "Application denied"


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(SQL_OUT / name)


def _json(name: str) -> dict | None:
    path = OUTPUT_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def data_facts() -> dict:
    con = connect()
    n, narr, d0, d1, last_narr = con.execute(
        """SELECT count(*), count(narrative), min(date_received), max(date_received),
                  max(date_received) FILTER (WHERE narrative IS NOT NULL) FROM complaints""").fetchone()
    all_cards, = con.execute("SELECT count(*) FROM cards_all").fetchone()
    amex, amex_narr = con.execute(
        "SELECT count(*), count(narrative) FROM complaints WHERE issuer = ?", [AMEX]).fetchone()
    return {"complaints": n, "narratives": narr, "first_date": str(d0), "last_date": str(d1),
            "last_narrative_date": str(last_narr), "all_card_complaints": all_cards,
            "amex_complaints": amex, "amex_narratives": amex_narr, "issuers": 7}


def sub_issue_facts() -> dict:
    mix = _read("04_sub_issue_mix_by_issuer.csv")
    relief = _read("09_relief_rate_by_sub_issue.csv").set_index("sub_issue")
    kw = _read("11_keyword_evidence_by_sub_issue.csv").set_index(["sub_issue", "issuer_group"])
    amex = mix[mix["issuer"] == AMEX].set_index("sub_issue")
    out = {}
    for key, sub in {"promo_terms": SUB_PROMO, "rewards": SUB_REWARDS, "fees": SUB_FEES,
                     "credit_limit": SUB_LIMIT, "application_denied": SUB_DENIED}.items():
        row = amex.loc[sub]
        entry = {
            "sub_issue": sub, "amex_complaints": int(row["complaints"]),
            "amex_share_pct": float(row["share_pct"]), "peers_share_pct": float(row["peers_share_pct"]),
            "diff_pts": float(row["diff_vs_peers_pts"]), "index_vs_peers": float(row["index_vs_peers"]),
            "amex_relief_pct": float(relief.loc[sub, "amex_monetary_relief_pct"]),
            "peers_relief_pct": float(relief.loc[sub, "peers_monetary_relief_pct"]),
        }
        if (sub, AMEX) in kw.index:
            a, p = kw.loc[(sub, AMEX)], kw.loc[(sub, "Other six issuers")]
            entry["keywords"] = {
                col.removesuffix("_pct"): {"amex_pct": float(a[col]), "peers_pct": float(p[col])}
                for col in kw.columns if col.endswith("_pct")
            }
            entry["amex_narratives"] = int(a["narratives"])
        out[key] = entry
    return out


def response_facts() -> dict:
    resp = _read("05_company_response_by_issuer.csv").set_index("issuer")
    timely = _read("06_timely_response_by_issuer_year.csv")
    return {
        "amex_monetary_relief_pct": float(resp.loc[AMEX, "monetary_relief_pct"]),
        "monetary_relief_by_issuer": resp["monetary_relief_pct"].to_dict(),
        "amex_relief_rank": int(resp["monetary_relief_pct"].rank(ascending=False)[AMEX]),
        "timely_pct_min": float(timely["timely_pct"].min()),
        "timely_pct_amex_min": float(timely[timely["issuer"] == AMEX]["timely_pct"].min()),
    }


def volume_facts() -> dict:
    vol = _read("08_complaints_per_purchase_volume.csv")
    y = vol[vol["year"] == 2024].sort_values("complaints_per_usd_bn").reset_index(drop=True)
    return {"year": 2024, "amex_per_usd_bn": float(y[y["issuer"] == AMEX]["complaints_per_usd_bn"].iloc[0]),
            "amex_rank_lowest_first": int(y.index[y["issuer"] == AMEX][0]) + 1,
            "lowest": {"issuer": y.loc[0, "issuer"], "rate": float(y.loc[0, "complaints_per_usd_bn"])},
            "highest": {"issuer": y.iloc[-1]["issuer"], "rate": float(y.iloc[-1]["complaints_per_usd_bn"])}}


def event_facts() -> dict:
    ev = pd.read_csv(OUTPUT_DIR / "event_study_summary.csv")
    out: dict = {}
    for event in ev["event"].unique():
        out[event] = {}
        for _, r in ev[ev["event"] == event].iterrows():
            out[event].setdefault(f"{r['lens']}:{r['metric']}", {})[str(int(r["window_months"]))] = {
                k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v))
                for k, v in r.items() if k not in ("event", "lens", "metric", "window_months", "description")}
    return out


def theme_facts() -> dict:
    summary = _json("theme_summary.json")
    peers = pd.read_csv(OUTPUT_DIR / "theme_amex_vs_peers.csv")
    return {**summary, "amex_vs_peers": peers.drop(columns=["label_source"]).to_dict("records")}


def llm_facts() -> dict:
    from classify import load_cache, spend_so_far  # local import: classify pulls in the SDK settings

    cache = load_cache()
    llm = llm_sample_labels()
    estimate = _json("cost_estimate.json")
    validation = _json("validation_metrics.json")
    to_label = VALIDATION_DIR / "to_label.csv"
    model = None if llm is None else str(llm["model"].iloc[0])
    used = cache[(cache["model"] == model) & (cache["status"] != "api_error")] if model else cache.iloc[0:0]
    prompt_tokens = float(used["input_tokens"].sum() + used["cache_read_tokens"].sum()) if len(used) else 0.0
    return {
        "labels_available": llm is not None,
        "model": model,
        "provider": None if model is None else PRICES[model].provider,
        "batch_priced": None if model is None else PRICES[model].batch,
        "sample_rows": int(len(pd.read_csv(OUTPUT_DIR / "sample_ids.csv"))),
        "requests_sent": int(used["pack_id"].nunique()) if len(used) else 0,
        "rows_without_valid_label": int((used["status"] != "ok").sum()) if len(used) else 0,
        "avg_output_tokens_per_row": round(float(used["output_tokens"].mean()), 1) if len(used) else None,
        "cache_read_share_of_input_pct": round(100 * float(used["cache_read_tokens"].sum()) / prompt_tokens, 1)
        if prompt_tokens else None,
        "narratives_cut_for_length": int(used["narrative_truncated"].fillna(False).sum()) if len(used) else 0,
        "rows_labeled": 0 if llm is None else len(llm),
        "rows_by_status": {} if cache.empty else cache["status"].value_counts().to_dict(),
        "api_spend_usd": round(spend_so_far(cache), 4) if not cache.empty else 0.0,
        "budget_usd": DEFAULT_BUDGET_USD,
        "cost_estimate": estimate,
        "validation_file_written": to_label.exists(),
        "validation": validation,
        "distill_report": _json("model_label_report.json"),
    }


def build_fixes(f: dict) -> list[dict]:
    s = f["sub_issues"]
    promo, rewards, fees, limit = s["promo_terms"], s["rewards"], s["fees"], s["credit_limit"]
    amex_ev = f["events"]["amex_platinum"]
    fee_mention = amex_ev["mention:annual_fee"]["12"]
    credit_mention = amex_ev["mention:statement_credit"]["12"]
    def z(x: float) -> str:  # avoid printing "-0.0"
        return f"{0.0 if abs(x) < 0.05 else x:.1f}"

    def llm_line(theme: str) -> str:
        """One sentence of LLM theme evidence, or nothing when the themes are not from the LLM."""
        if not f["themes_are_llm"]:
            return ""
        t = next(r for r in f["themes"]["amex_vs_peers"] if r["theme"] == theme)
        return (f" In the LLM theme labels, {t['theme_label'].lower()} is {t['amex_share_pct']:.1f}% of Amex "
                f"narratives against {t['peers_share_pct']:.1f}% at peers.")

    return [
        {
            "title": "Make welcome offer eligibility clear before the application is submitted.",
            "short": (f"Promotional terms complaints are {promo['amex_share_pct']:.1f}% of Amex complaints against "
                      f"{promo['peers_share_pct']:.1f}% at peers. Monetary relief {promo['amex_relief_pct']:.1f}% "
                      f"against {promo['peers_relief_pct']:.1f}%."),
            "evidence": (
                f"Promotional terms not received is {promo['amex_share_pct']:.1f}% of Amex complaints against "
                f"{promo['peers_share_pct']:.1f}% at the other six issuers ({promo['index_vs_peers']:.1f}x). "
                f"{promo['keywords']['welcome_offer']['amex_pct']:.0f}% of those Amex narratives mention a welcome or "
                f"bonus offer (peers {promo['keywords']['welcome_offer']['peers_pct']:.0f}%) and "
                f"{promo['keywords']['eligibility_wording']['amex_pct']:.0f}% use eligibility wording "
                f"(peers {promo['keywords']['eligibility_wording']['peers_pct']:.0f}%). Amex closes "
                f"{promo['amex_relief_pct']:.1f}% of them with monetary relief, peers {promo['peers_relief_pct']:.1f}%."
            ),
        },
        {
            "title": "Post rewards reliably and warn before points are lost.",
            "short": (f"Rewards complaints are {rewards['amex_share_pct']:.1f}% against {rewards['peers_share_pct']:.1f}% "
                      f"at peers. Monetary relief {rewards['amex_relief_pct']:.1f}% against {rewards['peers_relief_pct']:.1f}%."),
            "evidence": (
                f"Rewards problems are {rewards['amex_share_pct']:.1f}% of Amex complaints against "
                f"{rewards['peers_share_pct']:.1f}% at peers ({rewards['index_vs_peers']:.1f}x). "
                f"{rewards['keywords']['welcome_offer']['amex_pct']:.0f}% of the Amex narratives are about a welcome or "
                f"bonus offer and {rewards['keywords']['points_lost']['amex_pct']:.0f}% about points being forfeited or "
                f"taken back. Monetary relief: Amex {rewards['amex_relief_pct']:.1f}%, peers {rewards['peers_relief_pct']:.1f}%."
                + llm_line("rewards_points")
            ),
        },
        {
            "title": "Set a clear annual fee refund and renewal notice policy ahead of Platinum renewals.",
            "short": (f"{fees['keywords']['annual_fee']['amex_pct']:.0f}% of Amex fee narratives are about the annual fee "
                      f"against {fees['keywords']['annual_fee']['peers_pct']:.0f}% at peers. Monetary relief on fee "
                      f"complaints {fees['amex_relief_pct']:.1f}% against {fees['peers_relief_pct']:.1f}%."),
            "evidence": (
                f"{fees['keywords']['annual_fee']['amex_pct']:.0f}% of Amex fee narratives are about the annual fee "
                f"(peers {fees['keywords']['annual_fee']['peers_pct']:.0f}%) and "
                f"{fees['keywords']['refund']['amex_pct']:.0f}% ask about a refund. Amex grants monetary relief on "
                f"{fees['amex_relief_pct']:.1f}% of fee complaints, peers {fees['peers_relief_pct']:.1f}%. About "
                f"{fee_mention['treated_post_pct']:.0f}% of all Amex narratives mention the annual fee against "
                f"{fee_mention['control_post_pct']:.0f}% at comparison issuers. The rate did not rise after the Platinum "
                "refresh, so this is a standing issue, and existing members only began renewing at the new fee in January 2026."
                + llm_line("annual_fee")
            ),
        },
        {
            "title": "Make statement credits easy to track and fix posting-date edge cases.",
            "short": (f"Statement credit mentions went from {credit_mention['treated_pre_pct']:.1f}% to "
                      f"{credit_mention['treated_post_pct']:.1f}% of Amex narratives after the refresh. An early signal."),
            "evidence": (
                f"Statement credit mentions in Amex narratives went from {credit_mention['treated_pre_pct']:.1f}% in the "
                f"12 months before the Platinum refresh to {credit_mention['treated_post_pct']:.1f}% after, while "
                f"comparison issuers went from {credit_mention['control_pre_pct']:.1f}% to "
                f"{credit_mention['control_post_pct']:.1f}% (difference in differences "
                f"{credit_mention['did_pts']:+.1f} pts, 95% interval {z(credit_mention['did_ci_low_pts'])} to "
                f"{credit_mention['did_ci_high_pts']:.1f}). An early signal on small numbers, worth watching as the "
                "refreshed card adds more credits." + llm_line("statement_credit_benefit")
            ),
        },
        {
            "title": "Explain credit limit reductions when they happen.",
            "short": (f"Credit limit complaints are {limit['amex_share_pct']:.1f}% against "
                      f"{limit['peers_share_pct']:.1f}% at peers. The smallest of the five."),
            "evidence": (
                f"Credit limit decisions are {limit['amex_share_pct']:.1f}% of Amex complaints against "
                f"{limit['peers_share_pct']:.1f}% at peers ({limit['index_vs_peers']:.1f}x), on "
                f"{limit['amex_complaints']:,} complaints. Smaller than the items above, so it ranks last."
            ),
        },
    ]


def main() -> int:
    f: dict = {
        "data": data_facts(),
        "sub_issues": sub_issue_facts(),
        "responses": response_facts(),
        "volume": volume_facts(),
        "events": event_facts(),
        "themes": theme_facts(),
        "llm": llm_facts(),
    }
    source = f["themes"]["label_source"]
    f["label_source"] = source
    f["label_source_description"] = SOURCE_DESCRIPTION[source]
    f["themes_are_fallback"] = source == KEYWORD_FALLBACK
    f["themes_are_llm"] = source == LLM
    f["fixes"] = build_fixes(f)
    FINDINGS_JSON.write_text(json.dumps(f, indent=2, default=str), encoding="utf-8")
    print(f"wrote {FINDINGS_JSON}")
    for i, fix in enumerate(f["fixes"], 1):
        print(f"{i}. {fix['title']}\n   {fix['evidence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
