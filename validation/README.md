# Validation

Human check of the LLM theme labels.

## Steps

1. Run the classifier, then build the set:
   `python src/validation.py build`
   This writes `to_label.csv` with 150 complaints, spread evenly across the themes the model predicted,
   and `validation_design.csv` with the real mix of predicted themes.
2. Open `to_label.csv`. For each row read `narrative` and fill `human_primary_theme`:
   - type `ok` if the model's `llm_primary_theme` is right
   - otherwise type the correct theme key
   - leave it blank if you have not reviewed the row. Blank rows are left out of the score.
   `human_sentiment` is optional and works the same way.
3. Score it:
   `python src/validation.py score`
   This writes `validation_report.md` with agreement, Cohen's kappa, and precision and recall per theme.

## Theme keys

| Key | Meaning |
|---|---|
| `annual_fee` | The annual or membership fee itself |
| `statement_credit_benefit` | A credit or perk that did not work as expected |
| `rewards_points` | Points, miles, cash back, welcome bonus |
| `lounge_travel_benefit` | Lounge access, travel portal, hotel status, Global Entry credit |
| `insurance_protection_claim` | Purchase protection, trip delay, rental car, warranty claims |
| `dispute_fraud` | Disputed or unauthorized charges, identity theft |
| `customer_service` | Service is the main problem and no other theme explains it |
| `credit_limit_account_closure` | Limit changes, closures, application denials |
| `billing` | Payments, interest, late fees, credit reporting |
| `other` | None of the above, or too unclear to tell |

Sentiment keys: `very_negative`, `negative`, `neutral_or_mixed`.

## Reading the result

The reviewer sees the model's label, which can pull their judgment toward it. For a check without that
pull, build with `--blind` to get `to_label_blind.csv`, which has no model columns.
