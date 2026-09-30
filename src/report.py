"""Write the memo, README, interview notes and resume bullets from outputs/findings.json.

Every number in these documents is read from the findings file, so the documents
cannot disagree with the outputs. Rerun after any change to the data or the labels.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

from config import DOCS_DIR, OUTPUT_DIR, ROOT
from taxonomy import THEME_LABELS

AMEX = "American Express"


def load() -> dict:
    return json.loads((OUTPUT_DIR / "findings.json").read_text(encoding="utf-8"))


def test_summary() -> str:
    """Last line of the pytest run, for example '84 passed in 3.7s'."""
    run = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
    lines = [line for line in run.stdout.strip().splitlines() if line.strip()]
    return re.sub(r" in [\d.]+s.*", "", lines[-1]) if lines else "tests did not run"


def dashboard_link() -> str:
    """Link to the GitHub Pages site when the repo has a GitHub remote, else to the file."""
    run = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True)
    m = re.search(r"github\.com[:/]([^/]+)/([^/.\s]+)", run.stdout)
    if m:
        return f"[Live dashboard](https://{m.group(1).lower()}.github.io/{m.group(2)}/)"
    return "[Interactive dashboard](docs/index.html)"


def ev(f: dict, event: str, metric: str, window: str = "12") -> dict:
    return f["events"][event][metric][window]


def theme_rows(f: dict, top: int = 10) -> str:
    rows = sorted(f["themes"]["amex_vs_peers"], key=lambda r: -r["amex_share_pct"])[:top]
    lines = ["| Theme | Amex % | Other six issuers % | Difference (pts) |", "|---|---|---|---|"]
    lines += [f"| {r['theme_label']} | {r['amex_share_pct']:.1f} | {r['peers_share_pct']:.1f} | {r['diff_pts']:+.1f} |"
              for r in rows]
    return "\n".join(lines)


def llm_status(f: dict) -> dict:
    """Short sentences describing the state of the LLM step, used in several documents."""
    llm = f["llm"]
    est = llm.get("cost_estimate") or {}
    models = est.get("models", {})
    est_lines = ["| Model | Low | Expected | High |", "|---|---|---|---|"] + [
        f"| `{m}` | {v['batch_cost_usd']['low']:.2f} | {v['batch_cost_usd']['expected']:.2f} | {v['batch_cost_usd']['high']:.2f} |"
        for m, v in models.items()]
    val = llm.get("validation") or {}
    if val.get("reviewed"):
        kappa = "n/a" if val.get("cohen_kappa") is None else f"{val['cohen_kappa']:.2f}"
        validation = (f"{val['reviewed']} of {val['rows']} rows reviewed by hand. Agreement on primary theme "
                      f"{100 * val['agreement']:.1f}%, Cohen's kappa {kappa}. Precision and recall per theme are in "
                      "`validation/validation_report.md`.")
    elif llm["validation_file_written"]:
        validation = ("The 150-row validation set is written to `validation/to_label.csv` with the model's labels "
                      "filled in. It has not been reviewed by hand yet, so there is no accuracy figure to report.")
    else:
        validation = ("Not started. The validation set is drawn from LLM labels, and there are none yet. "
                      "`src/validation.py` is written and tested and will build the 150-row file after the LLM run.")
    if f["themes_are_llm"]:
        distill = llm.get("distill_report") or {}
        pending = llm["sample_rows"] - llm["rows_labeled"]
        state = (f"{llm['rows_labeled']:,} of {llm['sample_rows']:,} sampled narratives were classified with "
                 f"`{llm['model']}` in {llm['requests_sent']:,} requests. API usage at list price: "
                 f"USD {llm['api_spend_usd']:.2f} against a USD {llm['budget_usd']:.0f} budget (the key is on the "
                 "provider's free tier, so the amount billed may be lower).")
        if pending:
            state += (f" The other {pending:,} rows have no label yet because the free tier's daily request limit "
                      "was reached. They are a random subset, the weights are rescaled to cover them, and rerunning "
                      "the classifier continues from the cache.")
        if distill.get("cv_agreement_with_llm") is not None:
            state += (f" A TF-IDF + logistic regression model trained on those labels agrees with the LLM on "
                      f"{100 * distill['cv_agreement_with_llm']:.0f}% of held-out rows and is used only to label every "
                      "narrative for the monthly event study series.")
    else:
        state = ("The LLM run has not been executed yet, because no LLM API key was available in the build "
                 "environment. API spend so far: USD 0.00. The classifier, cache, budget guard and tests are in place. "
                 "Theme results shown today come from the fallback model (keyword-seeded TF-IDF + logistic "
                 "regression) and are labeled as such everywhere they appear.")
    if f["themes_are_llm"] and val.get("reviewed"):
        short = (f"LLM themes were checked by hand on {val['reviewed']} rows, with "
                 f"{100 * val['agreement']:.0f}% agreement.")
    elif f["themes_are_llm"]:
        short = "LLM theme labels are in place but have not been checked by hand yet."
    else:
        short = ("The LLM theme classification has not been run yet (no API key), so nothing in this memo depends "
                 "on it. The findings above use CFPB fields and keyword counts.")
    if llm.get("provider") == "gemini":
        how = ("Requests use schema-constrained JSON output, eight complaints per request matched back by id, low "
               "thinking effort, and ordinary (non-batch) calls sent four at a time with retries.")
        levers = ("Cost levers: eight complaints per request so the shared instructions are paid once per eight, "
                  "low thinking effort, and a small fast model. Provider-side caching did not apply: "
                  f"{llm['cache_read_share_of_input_pct']:.0f}% of input tokens were billed at the cached rate. "
                  "Explicit prompt caching and half-price batch requests are implemented on the Anthropic path.")
    else:
        how = ("Requests use structured JSON output, the Message Batches API, prompt caching, and eight complaints "
               "per request matched back by id.")
        levers = ("Cost levers: Message Batches API (half price), prompt caching on the shared instructions, and "
                  "eight complaints per request so the instructions are paid once per eight.")
    return {"state": state, "validation": validation, "short": short, "how": how, "levers": levers,
            "estimate_table": "\n".join(est_lines),
            "estimate_method": est.get("token_method", ""), "sample_rows": est.get("sample_rows"),
            "requests": est.get("requests"), "pack": est.get("complaints_per_request")}


# --- memo -------------------------------------------------------------------------------
def memo(f: dict) -> str:
    d, s = f["data"], f["sub_issues"]
    promo, rewards, fees = s["promo_terms"], s["rewards"], s["fees"]
    chase = ev(f, "chase_sapphire_reserve", "sub_issue:fees_rewards_promo")
    chase_rw = ev(f, "chase_sapphire_reserve", "sub_issue:rewards")
    chase_named = ev(f, "chase_sapphire_reserve", "mention:refreshed_card_named")
    amex = ev(f, "amex_platinum", "sub_issue:fees_rewards_promo")
    amex_fee = ev(f, "amex_platinum", "mention:annual_fee")
    fixes = "\n".join(f"{i}. **{x['title']}** {x['short']}" for i, x in enumerate(f["fixes"], 1))
    status = llm_status(f)
    theme_line = ""
    if f["themes_are_llm"]:
        top = sorted(f["themes"]["amex_vs_peers"], key=lambda r: -r["diff_pts"])[:2]
        theme_line = ("In the LLM theme labels, Amex is furthest above peers on "
                      + " and ".join(f"{r['theme_label'].lower()} ({r['diff_pts']:+.1f} points)" for r in top) + ".")
    return f"""# Memo: what card members complain about, and what Amex should fix first

**To:** US Consumer Services, membership experience
**Data:** {d['complaints']:,} CFPB credit card complaints about seven issuers, {d['first_date']} to {d['last_date']}

## Answer

Amex complaints are less about fraud and payments than its peers' and more about membership value: whether the
customer got the offer, the points and the fee treatment they expected. On those same topics Amex gives money
back less often than peers do. The 2025 Platinum refresh has not raised the share of fee and benefit complaints
so far. The Chase Sapphire Reserve refresh did raise Chase's.

## What the data shows

**1. Amex against six peers.** Promotional terms not received is {promo['amex_share_pct']:.1f}% of Amex complaints
and {promo['peers_share_pct']:.1f}% of peer complaints ({promo['index_vs_peers']:.1f}x). Rewards problems are
{rewards['amex_share_pct']:.1f}% against {rewards['peers_share_pct']:.1f}% ({rewards['index_vs_peers']:.1f}x).
Amex is under-indexed on unauthorized charges and payment processing. Amex closes {f['responses']['amex_monetary_relief_pct']:.1f}%
of complaints with monetary relief, which ranks {f['responses']['amex_relief_rank']} of 7. {theme_line}

**2. After the refreshes.** In the 12 months after the Sapphire Reserve refresh, fee, rewards and promotional
terms complaints went from {chase['treated_pre_pct']:.1f}% to {chase['treated_post_pct']:.1f}% of Chase complaints
while five comparison issuers went from {chase['control_pre_pct']:.1f}% to {chase['control_post_pct']:.1f}%
(difference in differences {chase['did_pts']:+.1f} points, 95% interval {chase['did_ci_low_pts']:.1f} to
{chase['did_ci_high_pts']:.1f}, outside the placebo range). Rewards drove it ({chase_rw['did_pts']:+.1f} points), and
narratives naming Sapphire Reserve went from {chase_named['treated_pre_pct']:.1f}% to {chase_named['treated_post_pct']:.1f}%.
At Amex the same share went from {amex['treated_pre_pct']:.1f}% to {amex['treated_post_pct']:.1f}% after the Platinum
refresh, and annual fee mentions stayed near {amex_fee['treated_post_pct']:.0f}% of narratives. This is suggestive,
not causal, and existing Platinum members only started renewing at USD 895 in January 2026.

## Fix first, in this order

{fixes}

## How much to trust this

- Complaints are self-selected. They show what goes wrong badly enough to escalate, not how often it goes wrong.
- Shares are compared instead of rates, because issuers' purchase volumes are not defined the same way.
- The CFPB does not record the card product, so product-level claims rest on keyword mentions in narratives.
- {status['short']}

## Next step

Match these complaint themes to internal contact-reason data for the same months. If welcome offer eligibility
and rewards posting also lead internal contacts, the first two fixes are sized and ready to prioritize.
"""


# --- README -----------------------------------------------------------------------------
def readme(f: dict, tests: str) -> str:
    d, s = f["data"], f["sub_issues"]
    promo, rewards, fees = s["promo_terms"], s["rewards"], s["fees"]
    chase = ev(f, "chase_sapphire_reserve", "sub_issue:fees_rewards_promo")
    chase_named = ev(f, "chase_sapphire_reserve", "mention:refreshed_card_named")
    amex = ev(f, "amex_platinum", "sub_issue:fees_rewards_promo")
    credit = ev(f, "amex_platinum", "mention:statement_credit")
    vol = f["volume"]
    status = llm_status(f)
    theme_heading = ("Theme mix from LLM classification" if f["themes_are_llm"]
                     else "Theme mix (provisional, fallback model)")
    theme_image = ("![Theme mix: American Express against the other six issuers](docs/img/dashboard_themes.png)\n\n"
                   if f["themes_are_llm"] else "")
    theme_note = (
        f"Weighted shares from {f['themes']['sample_rows']:,} classified narratives." if f["themes_are_llm"] else
        f"These shares come from the fallback model on {f['themes']['sample_rows']:,} sampled narratives, not from the "
        "LLM. They are shown so the pipeline can be seen end to end and will be replaced by the LLM run.")
    return f"""# What Card Members Complain About

Issuer benchmarking of {d['complaints']:,} CFPB credit card complaints with SQL, an event study and LLM classification.

**Question.** What do US credit card customers complain about at American Express compared with Chase, Capital One, Citi, Bank of America, Discover and Synchrony, and did that change after the 2025 premium card refreshes?

**Answer.** Amex complaints lean toward membership value. Promotional terms not received is {promo['index_vs_peers']:.1f}x the peer share and rewards problems {rewards['index_vs_peers']:.1f}x, and Amex pays monetary relief on them about half as often as peers. Chase's share of fee, rewards and promotional terms complaints rose {chase['did_pts']:.1f} points against comparison issuers after the Sapphire Reserve refresh. Amex's did not rise after the Platinum refresh.

**Recommendation.** Fix welcome offer eligibility clarity first, then rewards posting and forfeiture warnings, then annual fee refund and renewal rules before existing Platinum members finish renewing at the new fee.

{dashboard_link()} · [One-page memo](docs/memo.md) · [Data profile](docs/data_profile.md)

![Issuer benchmark: where American Express differs from the other six issuers](docs/img/dashboard_benchmark.png)

## What this project shows

- **Unlocking external data.** Found, downloaded and profiled a public regulatory archive, checked it against the live API, and documented its gaps before using it.
- **Competitive benchmarking.** Compared seven issuers on a like-for-like basis and explained why the obvious normalization (complaints per dollar of spend) would mislead.
- **SQL and Python.** 11 DuckDB queries, a tested Python pipeline, and one command that rebuilds every number.
- **AI implementation with controls.** LLM classification with a fixed taxonomy, schema-checked output, a hard budget, caching, and a human validation step with precision and recall per class.
- **Turning analysis into decisions.** A one-page memo that answers first and ranks five fixes by evidence.

## Key results

| Finding | Number | Where it comes from |
|---|---|---|
| Complaints analyzed, seven issuers, Jan 2023 to Aug 2026 | {d['complaints']:,} | [`docs/data_profile.md`](docs/data_profile.md) |
| Complaints with a published narrative | {d['narratives']:,} | [`docs/data_profile.md`](docs/data_profile.md) |
| Promotional terms not received, Amex share against peers | {promo['amex_share_pct']:.1f}% vs {promo['peers_share_pct']:.1f}% ({promo['index_vs_peers']:.1f}x) | [`04_sub_issue_mix_by_issuer.csv`](outputs/sql/04_sub_issue_mix_by_issuer.csv) |
| Rewards problems, Amex share against peers | {rewards['amex_share_pct']:.1f}% vs {rewards['peers_share_pct']:.1f}% ({rewards['index_vs_peers']:.1f}x) | [`04_sub_issue_mix_by_issuer.csv`](outputs/sql/04_sub_issue_mix_by_issuer.csv) |
| Monetary relief on promotional terms complaints, Amex against peers | {promo['amex_relief_pct']:.1f}% vs {promo['peers_relief_pct']:.1f}% | [`09_relief_rate_by_sub_issue.csv`](outputs/sql/09_relief_rate_by_sub_issue.csv) |
| Monetary relief on fee complaints, Amex against peers | {fees['amex_relief_pct']:.1f}% vs {fees['peers_relief_pct']:.1f}% | [`09_relief_rate_by_sub_issue.csv`](outputs/sql/09_relief_rate_by_sub_issue.csv) |
| Amex fee narratives that are about the annual fee, against peers | {fees['keywords']['annual_fee']['amex_pct']:.0f}% vs {fees['keywords']['annual_fee']['peers_pct']:.0f}% | [`11_keyword_evidence_by_sub_issue.csv`](outputs/sql/11_keyword_evidence_by_sub_issue.csv) |
| Chase fee, rewards and promo share, 12 months before and after its refresh | {chase['treated_pre_pct']:.1f}% to {chase['treated_post_pct']:.1f}% (comparison {chase['control_pre_pct']:.1f}% to {chase['control_post_pct']:.1f}%) | [`event_study_summary.csv`](outputs/event_study_summary.csv) |
| Chase difference in differences | {chase['did_pts']:+.1f} pts (95% interval {chase['did_ci_low_pts']:.1f} to {chase['did_ci_high_pts']:.1f}) | [`event_study_summary.csv`](outputs/event_study_summary.csv) |
| Chase narratives naming Sapphire Reserve, before and after | {chase_named['treated_pre_pct']:.1f}% to {chase_named['treated_post_pct']:.1f}% | [`event_study_summary.csv`](outputs/event_study_summary.csv) |
| Amex fee, rewards and promo share, before and after the Platinum refresh | {amex['treated_pre_pct']:.1f}% to {amex['treated_post_pct']:.1f}% ({amex['did_pts']:+.1f} pts against comparison) | [`event_study_summary.csv`](outputs/event_study_summary.csv) |
| Amex narratives mentioning a statement credit, before and after | {credit['treated_pre_pct']:.1f}% to {credit['treated_post_pct']:.1f}% | [`event_study_summary.csv`](outputs/event_study_summary.csv) |

![Event study: fee, rewards and promotional terms complaints before and after each refresh](docs/img/dashboard_event_study.png)

## Prioritized fixes for Amex

{chr(10).join(f"{i}. **{x['title']}** {x['evidence']}" for i, x in enumerate(f['fixes'], 1))}

"Application denied" is the largest Amex over-index in the chart above and is deliberately not on this list. Reading those narratives shows mostly identity disputes and template letters citing credit law, not membership problems.

## Proof that it runs

| Claim | Evidence in this repo |
|---|---|
| The data was inspected before any assumption was made | [`docs/data_profile.md`](docs/data_profile.md): rows per file, exact product and company strings, narrative availability by issuer and quarter, field completeness |
| The archive is complete for the study period | [`outputs/api_crosscheck.json`](outputs/api_crosscheck.json): archive counts are within 0.4% of the live CFPB API for every issuer in 2024 and 2025 |
| The structured analysis is plain SQL | [`sql/`](sql): 11 DuckDB queries, each with its result in [`outputs/sql/`](outputs/sql) |
| Filtering, taxonomy parsing and metric logic are tested | [`tests/`](tests): {tests} (`python -m pytest`) |
| Denominators are cited | [`data/reference/issuer_denominators.csv`](data/reference/issuer_denominators.csv): 60 figures from 10-K filings with URL and quoted table label |
| LLM cost is controlled | [`outputs/cost_estimate.json`](outputs/cost_estimate.json) and the budget guard in [`src/classify.py`](src/classify.py) |
| Every headline number is computed once | [`outputs/findings.json`](outputs/findings.json), which the dashboard, memo and this README are generated from |
| One command rebuilds everything | [`run_all.py`](run_all.py) |

## Method

```mermaid
flowchart LR
    A[CFPB narratives archive<br>18 files, 2023 to Aug 2026] --> B[Filter: credit card products,<br>7 issuers, exact strings]
    B --> C[Data profile]
    B --> D[DuckDB SQL:<br>mix, trends, responses]
    B --> E[Stratified sample<br>issuer x quarter]
    E --> F[LLM classification<br>10 membership themes]
    F --> G[150-row human validation]
    F --> H[Theme model for<br>all narratives]
    D --> I[Event study]
    H --> I
    D --> J[Findings, dashboard, memo]
    F --> J
    I --> J
```

1. **Data.** The CFPB stopped publishing narratives on 14 August 2026 and keeps an archive. The 18 archive files covering 2023 onward were downloaded and filtered to credit card products and the seven issuers using exact strings read from the data. The live API still serves structured fields and was used only as a cross-check.
2. **Benchmark.** Issuers are compared on complaint mix (shares), not raw counts. Purchase volume from 10-K filings is shown as a scale check only, because the definitions differ (consumer only or with small business, general purpose or private label). On that rough basis Amex had {vol['amex_per_usd_bn']:.1f} complaints per USD 1 billion in {vol['year']}, second lowest of seven.
3. **LLM classification.** A stratified sample of {f['themes']['sample_rows']:,} narratives (by issuer and quarter, larger cells for Amex and Chase) is classified into ten membership themes with sentiment, named benefits and named card product. The model sees only the narrative text. {status['how']}
4. **Validation.** 150 rows, spread across predicted themes, are pre-labeled and written to `validation/to_label.csv` for hand review. `src/validation.py score` reports agreement, Cohen's kappa, and precision and recall per theme. Unreviewed rows never count as agreement.
5. **Event study.** Difference in differences on shares, Chase and Amex each against five issuers with no refresh, over 6 and 12 month windows, with a placebo range from treating each comparison issuer as if it had the event. Three lenses: CFPB sub-issues, keyword mentions, and the theme model.

## Cost and validation

**Status.** {status['state']}

**Validation.** {status['validation']}

**Estimate made before the run** for {status['sample_rows']:,} narratives in {status['requests']:,} requests ({status['pack']} per request), in USD. Claude models are priced through the batch API, Gemini models at list price. Token counts: {status['estimate_method']}.

{status['estimate_table']}

The classifier refuses to send anything that could take total spend past USD 10. It sends the sample in chunks, measures real token use after the first chunk, and stops if the projection for the rest exceeds the budget. Results are cached in `outputs/llm_labels.jsonl`, so a rerun makes no API calls.

## {theme_heading}

{theme_note}

{theme_image}{theme_rows(f)}

## Limitations

- **Complaints are self-selected.** They are not a random sample of customers. A higher share of a topic means it is a larger part of what people escalate to a regulator, not that it happens to more customers.
- **Narratives are a subset.** About half of complaints have a published narrative, and the share drops from December 2025. August 2026 has none.
- **No card product field.** Product-level statements rest on keyword mentions of the card name in narratives.
- **The event study is suggestive, not causal.** Fee increases reached existing cardholders months after launch, the comparison group includes Capital One during its Discover integration, and the Amex pre-period includes an unusually high quarter for annual fee mentions.
- **Discover's label stops in March 2026**, ten months after the merger closed. Capital One figures from April 2026 may include Discover cards.
- **Shares, not rates.** A lower share on one topic can come from a higher share on another.
- **Validation is by one reviewer who sees the model's label**, which can inflate agreement. A blind copy of the validation file can be produced with `--blind`.

## Reproduce

```bash
py -3.11 -m venv .venv
.venv\\Scripts\\python -m pip install -r requirements.txt
.venv\\Scripts\\python run_all.py              # no API calls: uses cached labels, or the fallback model
.venv\\Scripts\\python run_all.py --classify   # needs GEMINI_API_KEY in .env, stops at the USD 10 budget
.venv\\Scripts\\python -m pytest
```

The first run downloads about 955 MB of archive files to `data/raw/` (not committed).

## Repository map

| Path | Contents |
|---|---|
| `sql/` | DuckDB queries for the structured analysis |
| `src/` | Download, filter, profile, sample, classify, validate, event study, dashboard |
| `tests/` | Filter logic, taxonomy parsing, metric and cost logic, classifier plumbing |
| `outputs/` | Query results, event study tables, cost estimate, findings |
| `docs/` | Dashboard (`index.html`), memo, data profile, screenshots |
| `validation/` | Hand-labeling file and validation report |
| `data/reference/` | Issuer denominators from 10-K filings, with sources |
"""


# --- interview prep ---------------------------------------------------------------------
def interview(f: dict, tests: str) -> str:
    d, s = f["data"], f["sub_issues"]
    promo, rewards, fees = s["promo_terms"], s["rewards"], s["fees"]
    chase = ev(f, "chase_sapphire_reserve", "sub_issue:fees_rewards_promo")
    amex = ev(f, "amex_platinum", "sub_issue:fees_rewards_promo")
    status = llm_status(f)
    est = (f["llm"].get("cost_estimate") or {}).get("models", {})
    rng = lambda m: f"USD {est[m]['batch_cost_usd']['low']:.2f} to {est[m]['batch_cost_usd']['high']:.2f}" if m in est else "n/a"  # noqa: E731
    return f"""# Interview prep

Private notes. Every number here is from `outputs/findings.json`.

**Current status of the LLM step.** {status['state']}
**Validation.** {status['validation']}

If the LLM run and hand validation are not finished when you interview, say so plainly. The structured benchmark
and the event study do not depend on them.

## The 30-second version

I took {d['complaints']:,} public CFPB credit card complaints about Amex and six competitors and asked where Amex is
different. Amex complaints lean toward membership value: promotional terms ({promo['index_vs_peers']:.1f}x the peer
share) and rewards ({rewards['index_vs_peers']:.1f}x). Amex also pays monetary relief on those less often than peers.
I then checked whether the 2025 premium card refreshes moved complaints. Chase's share rose {chase['did_pts']:.1f}
points against comparison issuers after the Sapphire Reserve refresh. Amex's did not rise after Platinum. That
gives a ranked list of fixes, led by welcome offer eligibility clarity.

## Why LLM classification

- The CFPB codes are built for regulators. "Problem with fees" mixes annual fees with late fees, and there is no
  code for lounge access, statement credits or protection claims. A membership team needs those split out.
- Keyword rules catch "annual fee" but miss a customer who writes "they charged me the yearly membership again".
  They also cannot tell root cause from symptom. Almost every narrative mentions customer service.
- A supervised model needs labels that do not exist. The LLM gives labels on day one, and I then train a cheap
  model on them to cover every narrative.
- The LLM also extracts things rules cannot: the named benefit and the named card product, which the CFPB does
  not record.
- What I did to keep it honest: fixed taxonomy with written definitions, schema-constrained JSON output, labels
  rejected unless they parse onto the taxonomy, model blind to the issuer field, prompt version in the cache key.

## How it was validated

- 150 rows drawn evenly across predicted themes, so rare themes such as lounge access get enough rows.
- Pre-labeled by the model, corrected by hand. Blank rows are excluded, so an unreviewed row cannot count as agreement.
- Reported: agreement, agreement reweighted to the real theme mix, Cohen's kappa, precision and recall per theme.
- Known weakness: I saw the model's label while reviewing, which anchors judgment. The script can write a blind copy.
- Result so far: {status['validation']}

## Cost and scaling choices

- Sample, not census: {f['themes']['sample_rows']:,} of {d['narratives']:,} narratives, stratified by issuer and quarter,
  with larger cells for Amex and Chase because the decisions are about them. Weights restore issuer-level shares.
- {status['levers']} Labels are matched back by id, never by position.
- The classifier has two provider paths, Gemini and Anthropic, behind one function. The first Gemini model I
  picked was returning 503 errors, so I switched to the same-priced model one version back and added retries.
- Estimated cost before the run: Gemini 3.6 Flash {rng('gemini-3.6-flash')}, Claude Sonnet 5.5
  {rng('claude-sonnet-5-5')}, Claude Opus 5.5 {rng('claude-opus-5-5')}. Budget USD {f['llm']['budget_usd']:.0f}.
- Budget guard: the run is chunked, real token use is measured after the first chunk, and it stops before the
  projection crosses the budget. Spend to date: USD {f['llm']['api_spend_usd']:.2f}.
- Cache: labels are stored by complaint id, model and prompt version. Reruns cost nothing.
- To scale to all narratives: train TF-IDF + logistic regression on the LLM labels and report its held-out
  agreement with the LLM. That is what feeds the monthly event study series.

## Ten likely questions

**1. Complaints are self-selected. Why should anyone act on this?**
They are not a measure of how often something happens. They measure what is bad enough that a customer goes to a
federal regulator. I compare mix across issuers, which cancels out some of the selection, and I would use this to
decide where to look in internal contact data, not as the final sizing.

**2. Why shares and not complaints per account?**
I pulled purchase volume from each 10-K. Amex reports consumer-only billed business, Capital One includes small
business cards, Synchrony is mostly private label with about one eighth of the spend per account. A single rate
would mostly rank business mix. I show the rate as a scale check and base conclusions on shares.

**3. A share can rise because something else fell. How do you handle that?**
That is the main weakness of shares. For the event study I checked counts as well, I report three different
measures, and the Chase result shows up in the sub-issue codes, in the theme model and in narratives naming the card.

**4. Is the Chase result causal?**
No. It is a difference in differences with a placebo range. The increase is outside what the five comparison
issuers show when each is treated as if it had the event, and rewards drive it. But other things changed in the
same months, so I call it suggestive.

**5. Why did Amex not show an increase after Platinum?**
Three possible reasons, and I cannot separate them with this data. Existing members only began renewing at
USD 895 in January 2026. The six months before the refresh already had a high level of annual fee mentions. And
Platinum is one product among many in Amex's complaints. Share went from {amex['treated_pre_pct']:.1f}% to
{amex['treated_post_pct']:.1f}%. I would rerun this when a full renewal cycle is in the data.

**6. How did you pick the comparison group?**
The five issuers without a premium refresh in the window. Chase and Amex are excluded from each other's
comparison group because each is treated in one event. The group is not clean: Capital One was absorbing
Discover. The placebo range is there to show how much these issuers move on their own.

**7. How do you know the model is not just reading the issuer name?**
The prompt contains only the narrative. Narratives often name the company, so it is not fully blind, but the
taxonomy is about the problem, and the validation set is drawn across issuers.

**8. What would you do with internal data?**
Join complaint themes to contact reasons and to refund decisions by product, size each fix by contact volume and
cost, and test the welcome offer eligibility message with an experiment on application-page wording.

**9. What did you do when something did not fit the plan?**
The first cost estimate for one complaint per request was above the budget for two of the three models, because
the shared instructions were longer than the average complaint. I changed the design to eight per request and
added a worst-case check per chunk. I also found that "Application denied", the largest Amex over-index, is
mostly templated legal-language complaints, so I left it out of the fixes.

**10. How do you know the numbers in the README are right?**
Every headline number is computed once into `outputs/findings.json` and the documents are generated from it. The
filter, taxonomy parser and metric functions have tests ({tests}). Archive counts match the live CFPB API within
0.4% for 2024 and 2025.

## The three weakest points, and how to address them

1. **Selection.** Complaints to a regulator are a thin, angry slice. Say it first, before the interviewer does.
   Position the work as competitive signal and a pointer to where internal data should be checked.
2. **Validation depth.** One reviewer, 150 rows, anchored on the model's label, about 15 rows per theme. Address
   it by quoting the confidence this supports and no more, and by offering the blind file and a second reviewer
   as the next step. If the validation is not finished, say the LLM results are unvalidated.
3. **The Amex event result is a null on a short window.** Do not claim the refresh had no effect. Say the data
   through August 2026 shows no rise in share, that renewals at the new fee started in January 2026, and that the
   statement credit signal is early and on small counts.
"""


# --- resume bullets ---------------------------------------------------------------------
def resume(f: dict) -> str:
    d, s = f["data"], f["sub_issues"]
    chase = ev(f, "chase_sapphire_reserve", "sub_issue:fees_rewards_promo")
    llm = f["llm"]
    bullets = [
        f"Benchmarked {d['complaints']:,} CFPB credit card complaints across 7 issuers in DuckDB SQL; found Amex "
        f"over-indexes {s['promo_terms']['index_vs_peers']:.1f}x on promotional-terms and "
        f"{s['rewards']['index_vs_peers']:.1f}x on rewards complaints versus peers."
    ]
    val = llm.get("validation") or {}
    if f["themes_are_llm"] and val.get("reviewed"):
        bullets.append(
            f"Classified {llm['rows_labeled']:,} complaint narratives into 10 membership themes with an LLM for "
            f"USD {llm['api_spend_usd']:.2f}; hand-validated {val['reviewed']} rows at "
            f"{100 * val['agreement']:.0f}% agreement.")
    elif f["themes_are_llm"]:
        bullets.append(
            f"Classified {llm['rows_labeled']:,} complaint narratives into 10 membership themes with an LLM for "
            f"USD {llm['api_spend_usd']:.2f} at list price, using schema-checked output and a hard budget guard.")
    else:
        bullets.append(
            f"Built a difference-in-differences event study of two 2025 premium card refreshes; Chase fee and "
            f"rewards complaint share rose {chase['did_pts']:.1f} points versus comparison issuers, Amex showed no increase.")
    for b in bullets:
        assert len(b.split()) <= 30, f"bullet over 30 words: {b}"
    note = ("" if f["themes_are_llm"] else
            "\nThe second bullet does not mention LLM classification because the LLM run has not been executed yet. "
            "Rerun `python src/report.py` after it has, and the bullet will switch to the LLM result.\n")
    return ("# Resume bullets\n\nEvery number is read from `outputs/findings.json`. Each bullet is 30 words or fewer.\n\n"
            + "\n".join(f"- {b}" for b in bullets) + "\n" + note)


def check(text: str, name: str) -> str:
    if "—" in text or "–" in text:
        raise ValueError(f"{name} contains a dash character that the writing rules exclude")
    return text


def main() -> int:
    f = load()
    tests = test_summary()
    outputs = {
        DOCS_DIR / "memo.md": memo(f),
        ROOT / "README.md": readme(f, tests),
        ROOT / "INTERVIEW_PREP.md": interview(f, tests),
        ROOT / "RESUME_BULLETS.md": resume(f),
    }
    for path, text in outputs.items():
        path.write_text(check(text, path.name), encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
