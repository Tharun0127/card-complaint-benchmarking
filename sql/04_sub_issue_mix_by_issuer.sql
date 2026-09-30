-- Sub-issue mix by issuer against the pooled other six issuers.
-- index_vs_peers above 1 means the issuer over-indexes on that sub-issue.
WITH counts AS (
    SELECT issuer, issue, coalesce(sub_issue, '(none)') AS sub_issue, count(*) AS n
    FROM complaints
    GROUP BY ALL
),
totals AS (
    SELECT issuer, count(*) AS issuer_total FROM complaints GROUP BY issuer
),
grid AS (
    SELECT t.issuer, t.issuer_total, s.issue, s.sub_issue
    FROM totals t CROSS JOIN (SELECT DISTINCT issue, sub_issue FROM counts) s
),
filled AS (
    SELECT g.issuer, g.issue, g.sub_issue, g.issuer_total, coalesce(c.n, 0) AS n
    FROM grid g LEFT JOIN counts c USING (issuer, issue, sub_issue)
),
with_peers AS (
    SELECT
        *,
        sum(n) OVER (PARTITION BY issue, sub_issue) - n AS peers_n,
        sum(issuer_total) OVER (PARTITION BY issue, sub_issue) - issuer_total AS peers_total
    FROM filled
)
SELECT
    issuer,
    issue,
    sub_issue,
    n AS complaints,
    round(100.0 * n / issuer_total, 2) AS share_pct,
    round(100.0 * peers_n / peers_total, 2) AS peers_share_pct,
    round(100.0 * n / issuer_total - 100.0 * peers_n / peers_total, 2) AS diff_vs_peers_pts,
    round((1.0 * n / issuer_total) / nullif(1.0 * peers_n / peers_total, 0), 2) AS index_vs_peers
FROM with_peers
WHERE n > 0
ORDER BY issuer, share_pct DESC;
