# What Card Members Complain About

Issuer benchmarking of 142,540 CFPB credit card complaints with SQL, an event study and LLM classification.

**Question.** What do US credit card customers complain about at American Express compared with Chase, Capital One, Citi, Bank of America, Discover and Synchrony, and did that change after the 2025 premium card refreshes?

**Answer.** Amex complaints lean toward membership value. Promotional terms not received is 2.5x the peer share and rewards problems 2.0x, and Amex pays monetary relief on them about half as often as peers. Chase's share of fee, rewards and promotional terms complaints rose 4.0 points against comparison issuers after the Sapphire Reserve refresh. Amex's did not rise after the Platinum refresh.

**Recommendation.** Fix welcome offer eligibility clarity first, then rewards posting and forfeiture warnings, then annual fee refund and renewal rules before existing Platinum members finish renewing at the new fee.

[Interactive dashboard](docs/index.html) · [One-page memo](docs/memo.md) · [Data profile](docs/data_profile.md)

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
| Complaints analyzed, seven issuers, Jan 2023 to Aug 2026 | 142,540 | [`docs/data_profile.md`](docs/data_profile.md) |
| Complaints with a published narrative | 69,518 | [`docs/data_profile.md`](docs/data_profile.md) |
| Promotional terms not received, Amex share against peers | 7.0% vs 2.8% (2.5x) | [`04_sub_issue_mix_by_issuer.csv`](outputs/sql/04_sub_issue_mix_by_issuer.csv) |
| Rewards problems, Amex share against peers | 6.3% vs 3.2% (2.0x) | [`04_sub_issue_mix_by_issuer.csv`](outputs/sql/04_sub_issue_mix_by_issuer.csv) |
| Monetary relief on promotional terms complaints, Amex against peers | 9.0% vs 20.5% | [`09_relief_rate_by_sub_issue.csv`](outputs/sql/09_relief_rate_by_sub_issue.csv) |
| Monetary relief on fee complaints, Amex against peers | 24.4% vs 38.7% | [`09_relief_rate_by_sub_issue.csv`](outputs/sql/09_relief_rate_by_sub_issue.csv) |
| Amex fee narratives that are about the annual fee, against peers | 35% vs 9% | [`11_keyword_evidence_by_sub_issue.csv`](outputs/sql/11_keyword_evidence_by_sub_issue.csv) |
| Chase fee, rewards and promo share, 12 months before and after its refresh | 16.6% to 20.0% (comparison 13.8% to 13.2%) | [`event_study_summary.csv`](outputs/event_study_summary.csv) |
| Chase difference in differences | +4.0 pts (95% interval 2.6 to 5.5) | [`event_study_summary.csv`](outputs/event_study_summary.csv) |
| Chase narratives naming Sapphire Reserve, before and after | 2.7% to 5.7% | [`event_study_summary.csv`](outputs/event_study_summary.csv) |
| Amex fee, rewards and promo share, before and after the Platinum refresh | 23.9% to 22.6% (-2.1 pts against comparison) | [`event_study_summary.csv`](outputs/event_study_summary.csv) |
| Amex narratives mentioning a statement credit, before and after | 3.0% to 4.5% | [`event_study_summary.csv`](outputs/event_study_summary.csv) |

![Event study: fee, rewards and promotional terms complaints before and after each refresh](docs/img/dashboard_event_study.png)

## Prioritized fixes for Amex

1. **Make welcome offer eligibility clear before the application is submitted.** Promotional terms not received is 7.0% of Amex complaints against 2.8% at the other six issuers (2.5x). 40% of those Amex narratives mention a welcome or bonus offer (peers 19%) and 21% use eligibility wording (peers 8%). Amex closes 9.0% of them with monetary relief, peers 20.5%.
2. **Post rewards reliably and warn before points are lost.** Rewards problems are 6.3% of Amex complaints against 3.2% at peers (2.0x). 27% of the Amex narratives are about a welcome or bonus offer and 11% about points being forfeited or taken back. Monetary relief: Amex 11.5%, peers 20.6%.
3. **Set a clear annual fee refund and renewal notice policy ahead of Platinum renewals.** 35% of Amex fee narratives are about the annual fee (peers 9%) and 30% ask about a refund. Amex grants monetary relief on 24.4% of fee complaints, peers 38.7%. About 10% of all Amex narratives mention the annual fee against 2% at comparison issuers. The rate did not rise after the Platinum refresh, so this is a standing issue, and existing members only began renewing at the new fee in January 2026.
4. **Make statement credits easy to track and fix posting-date edge cases.** Statement credit mentions in Amex narratives went from 3.0% in the 12 months before the Platinum refresh to 4.5% after, while comparison issuers went from 0.5% to 0.8% (difference in differences +1.1 pts, 95% interval 0.0 to 2.2). An early signal on small numbers, worth watching as the refreshed card adds more credits.
5. **Explain credit limit reductions when they happen.** Credit limit decisions are 2.4% of Amex complaints against 1.4% at peers (1.7x), on 388 complaints. Smaller than the items above, so it ranks last.

"Application denied" is the largest Amex over-index in the chart above and is deliberately not on this list. Reading those narratives shows mostly identity disputes and template letters citing credit law, not membership problems.

## Proof that it runs

| Claim | Evidence in this repo |
|---|---|
| The data was inspected before any assumption was made | [`docs/data_profile.md`](docs/data_profile.md): rows per file, exact product and company strings, narrative availability by issuer and quarter, field completeness |
| The archive is complete for the study period | [`outputs/api_crosscheck.json`](outputs/api_crosscheck.json): archive counts are within 0.4% of the live CFPB API for every issuer in 2024 and 2025 |
| The structured analysis is plain SQL | [`sql/`](sql): 11 DuckDB queries, each with its result in [`outputs/sql/`](outputs/sql) |
| Filtering, taxonomy parsing and metric logic are tested | [`tests/`](tests): 84 passed (`python -m pytest`) |
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
2. **Benchmark.** Issuers are compared on complaint mix (shares), not raw counts. Purchase volume from 10-K filings is shown as a scale check only, because the definitions differ (consumer only or with small business, general purpose or private label). On that rough basis Amex had 6.0 complaints per USD 1 billion in 2024, second lowest of seven.
3. **LLM classification.** A stratified sample of 4,436 narratives (by issuer and quarter, larger cells for Amex and Chase) is classified into ten membership themes with sentiment, named benefits and named card product. The model sees only the narrative text. Requests use structured JSON output, the Message Batches API, prompt caching, and eight complaints per request matched back by id.
4. **Validation.** 150 rows, spread across predicted themes, are pre-labeled and written to `validation/to_label.csv` for hand review. `src/validation.py score` reports agreement, Cohen's kappa, and precision and recall per theme. Unreviewed rows never count as agreement.
5. **Event study.** Difference in differences on shares, Chase and Amex each against five issuers with no refresh, over 6 and 12 month windows, with a placebo range from treating each comparison issuer as if it had the event. Three lenses: CFPB sub-issues, keyword mentions, and the theme model.

## Cost and validation

**Status.** The LLM run has not been executed yet, because no Anthropic API key was available in the build environment. API spend so far: USD 0.00. The classifier, cache, budget guard and tests are in place. Theme results shown today come from the fallback model (keyword-seeded TF-IDF + logistic regression) and are labeled as such everywhere they appear.

**Validation.** Not started. The validation set is drawn from LLM labels, and there are none yet. `src/validation.py` is written and tested and will build the 150-row file after the LLM run.

**Projected cost** for 4,436 narratives in 555 requests (8 per request), in USD at batch prices. Token counts: heuristic of 3.3 characters per token (no API key, so tokens were not counted).

| Model | Low | Expected | High |
|---|---|---|---|
| `claude-opus-5-5` | 6.92 | 10.44 | 19.89 |
| `claude-sonnet-5-5` | 3.52 | 5.26 | 9.95 |
| `claude-haiku-4-5` | 2.25 | 2.42 | 2.70 |

The classifier refuses to send anything that could take total spend past USD 10. It sends the sample in chunks, measures real token use after the first chunk, and stops if the projection for the rest exceeds the budget. Results are cached in `outputs/llm_labels.jsonl`, so a rerun makes no API calls.

## Theme mix (provisional, fallback model)

These shares come from the fallback model on 4,436 sampled narratives, not from the LLM. They are shown so the pipeline can be seen end to end and will be replaced by the LLM run.

| Theme | Amex % | Other six issuers % | Difference (pts) |
|---|---|---|---|
| Dispute or fraud | 33.0 | 32.6 | +0.4 |
| Billing | 18.5 | 27.4 | -8.9 |
| Customer service | 15.0 | 16.2 | -1.2 |
| Rewards and points | 11.5 | 6.2 | +5.2 |
| Other | 8.4 | 6.8 | +1.6 |
| Credit limit or account closure | 6.1 | 9.0 | -2.9 |
| Annual fee | 5.1 | 1.0 | +4.2 |
| Statement credit or benefit redemption | 1.4 | 0.5 | +0.9 |
| Insurance or protection claim | 0.9 | 0.3 | +0.6 |
| Lounge or travel benefit | 0.2 | 0.1 | +0.1 |

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
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run_all.py              # no API calls: uses cached labels, or the fallback model
.venv\Scripts\python run_all.py --classify   # needs ANTHROPIC_API_KEY, stops at the USD 10 budget
.venv\Scripts\python -m pytest
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
