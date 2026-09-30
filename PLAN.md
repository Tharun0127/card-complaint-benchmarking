# Plan: What Card Members Complain About

Issuer benchmarking of CFPB credit card complaints with LLM classification.
Target reader: a hiring manager for an Analyst role in American Express US Consumer Services.

## Business question

1. What do US credit card customers complain about at Amex versus Chase, Capital One, Citi,
   Bank of America, Discover and Synchrony?
2. Did complaints about fees, credits and benefits change after the 2025 premium card refreshes
   (Chase Sapphire Reserve, June 2025; Amex Platinum, 18 Sep 2025)?
3. Which membership pain points should Amex fix first?

## What I checked before planning (30 Sep 2026)

| Check | Result |
|---|---|
| CFPB narratives archive page | 21 zip exports, Dec 2011 to 14 Aug 2026. Files 4 to 21 cover Nov 2022 onward, about 955 MB zipped. |
| Live complaint database API | Responds with HTTP 200 and structured fields (product, issue, sub-issue, company, response, timely). No narrative field in the response I tested. |
| `ANTHROPIC_API_KEY` | Not set in this environment. The LLM step is blocked until it is. |
| Python | 3.11 available through the `py` launcher. |

## Data decisions

- Source of record: the archive files 4 to 21, filtered to `date_received >= 2023-01-01`.
  File 4 starts in Nov 2022, so it is downloaded and then trimmed.
- The live API is used only as a cross-check on structured counts and to see whether
  structured fields continue past 14 Aug 2026. It is not a source of narratives.
- Product filter: credit card products. Exact product and company strings are read from
  the data, not assumed. The mapping lives in `src/config.py` and is covered by tests.
- Normalization: look for US card purchase volume or accounts in each issuer's 10-K or
  investor materials. If the definitions are not comparable across issuers, fall back to
  issue mix (share of each issuer's complaints) and say so.

## Steps and commits

| # | Step | Output | Commit |
|---|---|---|---|
| 0 | Plan, repo scaffold, pinned requirements | `PLAN.md`, `requirements.txt`, `.gitignore` | 1 |
| 1 | Download archive files, inspect fields, filter to cards and 7 issuers | `data/processed/complaints.parquet` (not committed) | 2 |
| 2 | Profile the data | `docs/data_profile.md` | 3 |
| 3 | Structured analysis in DuckDB SQL | `sql/*.sql`, `outputs/*.csv` | 4 |
| 4 | Denominators from 10-K filings | `data/reference/issuer_denominators.csv`, cited | 5 |
| 5 | Stratified sample, taxonomy, LLM classifier with cost estimate and cache | `src/classify.py`, `outputs/cost_estimate.json` | 6 |
| 6 | Validation set and scoring script | `validation/to_label.csv`, `src/validate.py` | 7 |
| 7 | Fallback classifier (TF-IDF + logistic regression), clearly labeled | `src/fallback.py` | 8 |
| 8 | Event study | `outputs/event_study_*.csv` | 9 |
| 9 | Dashboard | `docs/index.html` | 10 |
| 10 | Memo, README, interview prep, resume bullets | `docs/memo.md`, `README.md`, `INTERVIEW_PREP.md`, `RESUME_BULLETS.md` | 11 |

Tests (`tests/`) cover the filter logic, taxonomy parsing and metric logic, and are added
alongside the code they test.

## LLM classification design

- Taxonomy (single primary theme): annual fee, statement credit or benefit redemption,
  rewards and points, lounge or travel benefit, insurance or protection claim, dispute or
  fraud, customer service, credit limit or account closure, billing, other.
- Also extracted: sentiment and any named benefit.
- Sample: stratified by issuer and quarter, 3,000 to 5,000 narratives.
- Cost control: a dry run estimates tokens and cost first. Hard stop above USD 10 without
  approval. Message Batches API (50% discount), prompt caching on the shared system
  prompt, structured JSON output.
- Cache: every result is written to `data/llm_cache/` keyed by complaint id, prompt version
  and model, so reruns make no API calls.
- Validation: 150 rows, pre-labeled by the model, written to `validation/to_label.csv` for
  hand review. `src/validate.py` computes agreement, Cohen's kappa, and precision and recall
  per class once the human column is filled in.
- If the key is missing: stop and report. If the API itself is unavailable: TF-IDF plus
  logistic regression, labeled as a fallback everywhere it appears.

## Event study design

- Outcome: share of an issuer's card complaints that are about fees, credits or benefits.
- Treated: Chase around the Sapphire Reserve refresh, Amex around the Platinum refresh.
- Comparison: the other issuers over the same windows.
- Reported as a simple difference in differences on monthly shares. It is suggestive, not
  causal: complaints are self-selected, the database does not identify the card product,
  and other things changed in the same months.

## Known risks

- Narratives are published only with consumer consent, so narrative coverage differs by
  issuer and may not match the full complaint mix.
- The archive contains only complaints that were published, which requires a company
  response or 15 days, so the last weeks before 14 Aug 2026 may be thin.
- Capital One completed its acquisition of Discover in May 2025. Company labels in the data
  may or may not reflect that. This is checked in the profile.
- Complaints to the CFPB are not a random sample of customers.

## Working rules

Python 3.11, pinned requirements, one commit per step, no API key or raw data in git,
plain writing, no invented numbers.
