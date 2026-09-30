-- Views used by every query in this folder. run_sql.py executes this file first and
-- replaces {complaints_parquet}, {cards_all_parquet} and {denominators_csv} with paths.

CREATE OR REPLACE VIEW complaints AS
SELECT
    *,
    date_trunc('month', date_received)::DATE AS month,
    date_trunc('quarter', date_received)::DATE AS quarter_start,
    strftime(date_received, '%Y') || '-Q' || quarter(date_received) AS quarter,
    year(date_received) AS year,
    narrative IS NOT NULL AS has_narrative,
    -- CFPB sub-issues that are about what the card costs and what it gives back.
    -- This is the structured-field proxy for "fee, credit and benefit" complaints.
    CASE sub_issue
        WHEN 'Problem with fees' THEN 'Fees'
        WHEN 'Problem with rewards from credit card' THEN 'Rewards'
        WHEN 'Didn''t receive advertised or promotional terms' THEN 'Promotional terms not received'
        WHEN 'Confusing or misleading advertising about the credit card' THEN 'Confusing advertising'
    END AS value_issue
FROM read_parquet('{complaints_parquet}');

CREATE OR REPLACE VIEW cards_all AS
SELECT *, date_trunc('month', date_received)::DATE AS month, year(date_received) AS year
FROM read_parquet('{cards_all_parquet}');

-- Purchase volume by issuer and year from 10-K filings. Citi reports Branded Cards and
-- Retail Services separately, so the two lines are added together.
CREATE OR REPLACE VIEW purchase_volume AS
SELECT
    CASE issuer WHEN 'JPMorgan Chase' THEN 'Chase' ELSE issuer END AS issuer,
    fiscal_year AS year,
    sum(value) AS purchase_volume_usd_bn
FROM read_csv('{denominators_csv}', header = true)
WHERE metric = 'purchase_volume_usd_bn'
GROUP BY ALL;
