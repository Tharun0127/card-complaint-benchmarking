-- Monthly panel for the event study: complaints about fees, rewards and promotional
-- terms (CFPB sub-issues) as a count and as a share of each issuer's complaints.
SELECT
    issuer,
    month,
    count(*) AS complaints,
    count(*) FILTER (WHERE value_issue IS NOT NULL) AS value_complaints,
    count(*) FILTER (WHERE value_issue = 'Fees') AS fees,
    count(*) FILTER (WHERE value_issue = 'Rewards') AS rewards,
    count(*) FILTER (WHERE value_issue = 'Promotional terms not received') AS promo_terms,
    count(*) FILTER (WHERE value_issue = 'Confusing advertising') AS confusing_advertising,
    round(100.0 * count(*) FILTER (WHERE value_issue IS NOT NULL) / count(*), 2) AS value_share_pct
FROM complaints
GROUP BY issuer, month
ORDER BY issuer, month;
