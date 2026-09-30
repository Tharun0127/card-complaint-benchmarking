-- Issue mix: each CFPB issue as a share of the issuer's complaints, compared with the
-- pooled share across the other six issuers. Shares are used instead of raw counts
-- because the issuers differ in size and the available denominators are not comparable.
WITH counts AS (
    SELECT issuer, issue, count(*) AS n
    FROM complaints
    GROUP BY issuer, issue
),
totals AS (
    SELECT issuer, count(*) AS issuer_total FROM complaints GROUP BY issuer
),
grid AS (
    SELECT t.issuer, t.issuer_total, i.issue
    FROM totals t CROSS JOIN (SELECT DISTINCT issue FROM complaints) i
),
filled AS (
    SELECT g.issuer, g.issue, g.issuer_total, coalesce(c.n, 0) AS n
    FROM grid g LEFT JOIN counts c USING (issuer, issue)
),
with_peers AS (
    SELECT
        *,
        sum(n) OVER (PARTITION BY issue) - n AS peers_n,
        sum(issuer_total) OVER (PARTITION BY issue) - issuer_total AS peers_total
    FROM filled
)
SELECT
    issuer,
    issue,
    n AS complaints,
    round(100.0 * n / issuer_total, 2) AS share_pct,
    round(100.0 * peers_n / peers_total, 2) AS peers_share_pct,
    round(100.0 * n / issuer_total - 100.0 * peers_n / peers_total, 2) AS diff_vs_peers_pts,
    round((1.0 * n / issuer_total) / nullif(1.0 * peers_n / peers_total, 0), 2) AS index_vs_peers
FROM with_peers
ORDER BY issuer, share_pct DESC;
