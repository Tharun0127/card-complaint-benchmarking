-- What the narratives inside the fee, rewards and promotional-terms sub-issues are about:
-- American Express against the other six issuers. The CFPB sub-issue says "fees" or
-- "rewards"; these keyword rates show which fee and which part of rewards.
WITH tagged AS (
    SELECT
        sub_issue,
        CASE WHEN issuer = 'American Express' THEN 'American Express' ELSE 'Other six issuers' END AS issuer_group,
        regexp_matches(narrative, '(?i)welcome (offer|bonus)|sign[- ]?up bonus|bonus (offer|points|miles)|\d{2,3},?000 (points|miles)')
            AS welcome_offer,
        regexp_matches(narrative, '(?i)not eligible|ineligible|pop[- ]?up|once per lifetime|lifetime') AS eligibility,
        regexp_matches(narrative, '(?i)annual (membership )?fee|membership fee') AS annual_fee,
        regexp_matches(narrative, '(?i)late fee') AS late_fee,
        regexp_matches(narrative, '(?i)refund') AS refund,
        regexp_matches(narrative, '(?i)statement credit') AS statement_credit,
        regexp_matches(narrative, '(?i)forfeit|claw|took (back|away)|removed (the|my) points|rescind') AS points_lost
    FROM complaints
    WHERE has_narrative AND value_issue IS NOT NULL
)
SELECT
    sub_issue,
    issuer_group,
    count(*) AS narratives,
    round(100.0 * count(*) FILTER (WHERE welcome_offer) / count(*), 1) AS welcome_offer_pct,
    round(100.0 * count(*) FILTER (WHERE eligibility) / count(*), 1) AS eligibility_wording_pct,
    round(100.0 * count(*) FILTER (WHERE annual_fee) / count(*), 1) AS annual_fee_pct,
    round(100.0 * count(*) FILTER (WHERE late_fee) / count(*), 1) AS late_fee_pct,
    round(100.0 * count(*) FILTER (WHERE refund) / count(*), 1) AS refund_pct,
    round(100.0 * count(*) FILTER (WHERE statement_credit) / count(*), 1) AS statement_credit_pct,
    round(100.0 * count(*) FILTER (WHERE points_lost) / count(*), 1) AS points_lost_pct
FROM tagged
GROUP BY sub_issue, issuer_group
ORDER BY sub_issue, issuer_group;
