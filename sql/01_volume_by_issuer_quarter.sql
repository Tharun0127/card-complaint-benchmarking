-- Complaint volume and narrative availability by issuer and quarter.
SELECT
    issuer,
    quarter,
    count(*) AS complaints,
    count(*) FILTER (WHERE has_narrative) AS with_narrative,
    round(100.0 * count(*) FILTER (WHERE has_narrative) / count(*), 1) AS narrative_pct
FROM complaints
GROUP BY issuer, quarter
ORDER BY issuer, quarter;
