-- Monetary relief rate by sub-issue: American Express against the other six issuers.
-- A sub-issue where Amex over-indexes on volume and grants relief less often than
-- peers is a candidate for a fix. Sub-issues with fewer than 100 Amex complaints are dropped.
WITH closed AS (
    SELECT *, issuer = 'American Express' AS is_amex
    FROM complaints
    WHERE company_response <> 'In progress'
)
SELECT
    issue,
    sub_issue,
    count(*) FILTER (WHERE is_amex) AS amex_complaints,
    round(100.0 * count(*) FILTER (WHERE is_amex AND company_response = 'Closed with monetary relief')
          / count(*) FILTER (WHERE is_amex), 1) AS amex_monetary_relief_pct,
    count(*) FILTER (WHERE NOT is_amex) AS peers_complaints,
    round(100.0 * count(*) FILTER (WHERE NOT is_amex AND company_response = 'Closed with monetary relief')
          / count(*) FILTER (WHERE NOT is_amex), 1) AS peers_monetary_relief_pct
FROM closed
GROUP BY issue, sub_issue
HAVING count(*) FILTER (WHERE is_amex) >= 100
ORDER BY amex_complaints DESC;
