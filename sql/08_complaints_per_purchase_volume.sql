-- Complaints per USD 1 billion of card purchase volume, by issuer and year.
-- A rough scale check only. The purchase volume definitions differ by issuer
-- (see data/reference/denominator_research.md), so this is not used to rank issuers.
-- 2025 is left out for Capital One and Discover because the acquisition closed mid-year.
SELECT
    c.issuer,
    c.year,
    count(*) AS complaints,
    p.purchase_volume_usd_bn,
    round(count(*) / p.purchase_volume_usd_bn, 2) AS complaints_per_usd_bn
FROM complaints c
JOIN purchase_volume p ON p.issuer = c.issuer AND p.year = c.year
WHERE c.year IN (2023, 2024, 2025)
  AND NOT (c.year = 2025 AND c.issuer IN ('Capital One', 'Discover'))
GROUP BY c.issuer, c.year, p.purchase_volume_usd_bn
ORDER BY c.year, complaints_per_usd_bn;
