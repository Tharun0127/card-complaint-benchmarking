"""Build docs/index.html: a single self-contained page (Plotly is inlined) for GitHub Pages."""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs

from config import CONTROL_ISSUERS, DOCS_DIR, EVENTS, OUTPUT_DIR
from filters import ISSUERS
from labels import KEYWORD_FALLBACK, LLM
from taxonomy import THEME_KEYS, THEME_LABELS

SQL_OUT = OUTPUT_DIR / "sql"
TEMPLATE = Path(__file__).with_name("dashboard_template.html")
OUT = DOCS_DIR / "index.html"
AMEX = "American Express"

METRICS = [
    ("sub_issue:fees_rewards_promo", "Fee, rewards and promotional terms complaints (CFPB sub-issues, all complaints)"),
    ("sub_issue:rewards", "Rewards complaints (CFPB sub-issue, all complaints)"),
    ("sub_issue:fees", "Fee complaints (CFPB sub-issue, all complaints)"),
    ("mention:annual_fee", "Narratives that mention the annual fee"),
    ("mention:statement_credit", "Narratives that mention a statement credit"),
    ("mention:refreshed_card_named", "Narratives that name the refreshed card"),
    ("theme:membership_value", "Fee, credit and benefit themes (theme model, all narratives)"),
]


def records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records"))


def heat(df: pd.DataFrame, row: str, col: str, value: str, rows: list[str], cols: list[str],
         col_labels: dict | None = None) -> dict:
    pivot = df.pivot(index=row, columns=col, values=value).reindex(index=rows, columns=cols).fillna(0)
    return {"rows": rows, "columns": [(col_labels or {}).get(c, c) for c in cols],
            "z": pivot.round(1).values.tolist()}


def benchmark(f: dict) -> dict:
    sub = pd.read_csv(SQL_OUT / "04_sub_issue_mix_by_issuer.csv")
    amex = sub[(sub["issuer"] == AMEX) & (sub["complaints"] >= 150)].sort_values("diff_vs_peers_pts", ascending=False)
    amex = pd.concat([amex.head(7), amex.tail(6)])
    subissue = [{"label": r.sub_issue, "amex": r.share_pct, "peers": r.peers_share_pct,
                 "diff": r.diff_vs_peers_pts, "n": int(r.complaints)} for r in amex.itertuples()]

    issue = pd.read_csv(SQL_OUT / "03_issue_mix_by_issuer.csv")
    top_issues = issue.groupby("issue")["complaints"].sum().nlargest(9).index.tolist()
    issue_heat = heat(issue, "issuer", "issue", "share_pct", ISSUERS, top_issues)

    resp = pd.read_csv(SQL_OUT / "05_company_response_by_issuer.csv")
    relief = [{"issuer": r.issuer, "pct": r.monetary_relief_pct, "n": int(r.closed_complaints)}
              for r in resp.itertuples()]
    relief_sub = [{"label": s["sub_issue"], "amex": s["amex_relief_pct"], "peers": s["peers_relief_pct"]}
                  for key, s in f["sub_issues"].items() if key in ("fees", "promo_terms", "rewards")]

    trend = pd.read_csv(SQL_OUT / "02_monthly_trend.csv", parse_dates=["month"])
    base = trend[trend["month"].dt.year == 2023].groupby("issuer")["complaints"].mean()
    trend["index"] = 100 * trend["complaints_3m_avg"] / trend["issuer"].map(base)
    trend_out = [{"issuer": issuer, "month": g["month"].dt.strftime("%Y-%m-%d").tolist(),
                  "index": g["index"].round(1).tolist()} for issuer, g in trend.groupby("issuer")]

    vol = pd.read_csv(SQL_OUT / "08_complaints_per_purchase_volume.csv")
    to_rows = lambda d: [{"issuer": r.issuer, "year": int(r.year), "complaints": int(r.complaints),  # noqa: E731
                          "volume": r.purchase_volume_usd_bn, "rate": r.complaints_per_usd_bn}
                         for r in d.itertuples()]
    return {
        "subissue_diff": subissue, "issue_heat": issue_heat, "relief": relief, "relief_sub": relief_sub,
        "trend": trend_out,
        "per_volume": to_rows(vol[vol["year"] == 2024].sort_values("complaints_per_usd_bn")),
        "per_volume_all": to_rows(vol.sort_values(["year", "complaints_per_usd_bn"])),
        "per_volume_note": (
            "2024, the last year in which all seven issuers reported separately. Purchase volume is from each "
            "issuer's 10-K. The definitions differ (consumer only or with small business cards, private label "
            "or general purpose), so read this as a rough check on scale and not as a ranking."),
    }


def themes(f: dict) -> dict:
    peers = pd.DataFrame(f["themes"]["amex_vs_peers"])
    peers = peers.set_index("theme").reindex(THEME_KEYS).reset_index()
    rows = [{"label": r.theme_label, "amex": r.amex_share_pct, "lo": r.amex_ci_low_pct, "hi": r.amex_ci_high_pct,
             "peers": r.peers_share_pct, "diff": r.diff_pts, "n": int(r.amex_sample_rows)}
            for r in peers.itertuples()]
    mix = pd.read_csv(OUTPUT_DIR / "theme_mix_by_issuer.csv")
    out = {"theme_vs_peers": rows,
           "theme_heat": heat(mix, "issuer", "theme", "share_pct", ISSUERS, THEME_KEYS, THEME_LABELS),
           "benefits": None, "sentiment": None}
    benefits, sentiment = OUTPUT_DIR / "named_benefits_top.csv", OUTPUT_DIR / "theme_sentiment_amex.csv"
    if f["themes_are_llm"] and benefits.exists():
        b = pd.read_csv(benefits)
        out["benefits"] = records(b[b["group"] == AMEX].head(12)[["name", "mentions"]])
    if f["themes_are_llm"] and sentiment.exists():
        s = pd.read_csv(sentiment)
        s = s[s["sentiment"] == "very_negative"].sort_values("share_pct", ascending=False)
        out["sentiment"] = [{"label": r.theme_label, "pct": r.share_pct} for r in s.itertuples()]
    return out


def events(f: dict) -> dict:
    monthly = pd.read_csv(OUTPUT_DIR / "event_study_monthly.csv")
    summary = pd.read_csv(OUTPUT_DIR / "event_study_summary.csv")
    descriptions = {f"{r.lens}:{r.metric}": r.description for r in summary.itertuples()}
    out = []
    for event in EVENTS:
        metrics = {}
        for key, _ in METRICS:
            lens, metric = key.split(":")
            m = monthly[(monthly["event"] == event["key"]) & (monthly["lens"] == lens) & (monthly["metric"] == metric)]
            series = {}
            for group in ("treated", "comparison"):
                g = m[m["group"] == group].sort_values("month")
                series[group] = {"month": g["month"].tolist(), "share": g["share_pct_3m"].tolist()} if len(g) else None
            s = summary[(summary["event"] == event["key"]) & (summary["lens"] == lens) & (summary["metric"] == metric)]
            none = lambda v: None if pd.isna(v) else float(v)  # noqa: E731
            metrics[key] = {**series, "summary": [
                {"window": int(r.window_months), "t_pre": none(r.treated_pre_pct), "t_post": none(r.treated_post_pct),
                 "c_pre": none(r.control_pre_pct), "c_post": none(r.control_post_pct), "did": none(r.did_pts),
                 "lo": none(r.did_ci_low_pts), "hi": none(r.did_ci_high_pts),
                 "p_min": none(r.placebo_did_min_pts), "p_max": none(r.placebo_did_max_pts)}
                for r in s.sort_values("window_months").itertuples()]}
        out.append({"key": event["key"], "label": event["label"], "issuer": event["issuer"],
                    "event_month": event["event_month"], "detail": event["detail"],
                    "short_label": pd.Timestamp(event["event_date"]).strftime("%d %b %Y"), "metrics": metrics})
    theme_note = " Uses the fallback theme model, not the LLM." if f["themes_are_fallback"] else ""
    return {"events": out, "metrics": [
        {"key": key, "label": label,
         "description": descriptions[key] + ". Lines are three-month averages. Comparison issuers: "
                        + ", ".join(CONTROL_ISSUERS) + "." + (theme_note if key.startswith("theme:") else "")}
        for key, label in METRICS]}


def text_blocks(f: dict) -> dict:
    d, s = f["data"], f["sub_issues"]
    chase = f["events"]["chase_sapphire_reserve"]["sub_issue:fees_rewards_promo"]["12"]
    amex = f["events"]["amex_platinum"]["sub_issue:fees_rewards_promo"]["12"]
    lede = (
        f"{d['complaints']:,} credit card complaints to the CFPB about seven US issuers, January 2023 to August 2026. "
        f"American Express stands out on membership value: promotional terms not received "
        f"({s['promo_terms']['index_vs_peers']:.1f}x the peer share) and rewards ({s['rewards']['index_vs_peers']:.1f}x). "
        f"After the Sapphire Reserve refresh, the share of Chase complaints about fees, rewards and promotional terms rose "
        f"from {chase['treated_pre_pct']:.1f}% to {chase['treated_post_pct']:.1f}% while comparison issuers were flat. "
        f"After the Platinum refresh, the same share at Amex did not rise "
        f"({amex['treated_pre_pct']:.1f}% to {amex['treated_post_pct']:.1f}%)."
    )
    llm = f["llm"]
    if f["themes_are_llm"]:
        banner = None
        theme_sub = (
            f"Themes come from LLM classification ({llm['model']}) of a stratified sample of "
            f"{f['themes']['sample_rows']:,} narratives, weighted back to all narratives for each issuer. "
            "The LLM saw only the narrative text, not the issuer name field.")
        quotes_sub = "Short excerpts from CFPB narratives in the classified sample, grouped by the LLM's theme. At most three per theme."
    else:
        banner = (
            "Section 2 and the quote grouping currently use a FALLBACK theme model (keyword-seeded TF-IDF + logistic "
            "regression), because no Anthropic API key was available when this page was built. It is not LLM "
            "classification and has not been validated against human labels. Sections 1 and 3 use CFPB fields and "
            "keyword counts and do not depend on it, except the measure marked 'theme model'.")
        theme_sub = (
            f"FALLBACK labels on a stratified sample of {f['themes']['sample_rows']:,} narratives, weighted back to all "
            "narratives for each issuer. Treat this section as provisional until the LLM run replaces it.")
        quotes_sub = "Short excerpts from CFPB narratives in the sample, grouped by the fallback theme model. At most three per theme."
    validation = llm.get("validation") or {}
    if validation.get("reviewed"):
        val_text = (f"Human validation: {validation['reviewed']} rows reviewed, "
                    f"{100 * validation['agreement']:.1f}% agreement on primary theme.")
    elif llm["validation_file_written"]:
        val_text = "Human validation: the 150-row set has been written and is waiting for hand labels."
    else:
        val_text = "Human validation: not started, because there are no LLM labels yet."
    footer = (
        "<p><strong>Source.</strong> CFPB Consumer Complaint Database narratives archive, credit card complaints received "
        f"{d['first_date']} to {d['last_date']}. Narratives run to {d['last_narrative_date']}.</p>"
        "<p><strong>Limits.</strong> Complaints are self-selected and are not a random sample of customers. Narratives are "
        "published only with consumer consent, and the narrative share falls from December 2025. The CFPB does not "
        "record the card product. Discover's company label stops in March 2026 after its merger into Capital One.</p>"
        f"<p><strong>Labels.</strong> {html.escape(f['label_source_description'])}. {val_text} "
        f"API spend to date: USD {llm['api_spend_usd']:.2f}.</p>"
    )
    tiles = [
        {"value": f"{d['complaints']:,}", "label": "complaints, seven issuers"},
        {"value": f"{d['narratives']:,}", "label": "with a narrative"},
        {"value": f"{d['amex_complaints']:,}", "label": "about American Express"},
        {"value": f"{s['promo_terms']['index_vs_peers']:.1f}x", "label": "Amex share of promotional terms complaints against peers"},
        {"value": f"{chase['did_pts']:+.1f} pts", "label": "Chase fee, rewards and promo share after its refresh, against comparison issuers"},
    ]
    return {"lede": lede, "banner": banner, "theme_sub": theme_sub, "quotes_sub": quotes_sub,
            "footer": footer, "tiles": tiles}


def quotes() -> list[dict]:
    q = json.loads((OUTPUT_DIR / "example_quotes.json").read_text(encoding="utf-8"))["quotes"]
    return [{"label": THEME_LABELS[theme],
             "items": [{"text": html.escape(i["text"]), "issuer": i["issuer"], "quarter": i["quarter"]}
                       for i in items[:3]]}
            for theme, items in q.items() if items]


def main() -> int:
    f = json.loads((OUTPUT_DIR / "findings.json").read_text(encoding="utf-8"))
    data = {**benchmark(f), **themes(f), **events(f), **text_blocks(f), "quotes": quotes(),
            "fixes": [{"title": html.escape(x["title"]), "evidence": html.escape(x["evidence"])} for x in f["fixes"]]}
    page = TEMPLATE.read_text(encoding="utf-8")
    page = page.replace("/*__PLOTLY__*/", get_plotlyjs())
    page = page.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
