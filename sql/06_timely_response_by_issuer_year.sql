-- Timely response rate by issuer and year, as recorded by the CFPB.
SELECT
    issuer,
    year,
    count(*) AS complaints,
    count(*) FILTER (WHERE timely_response = 'No') AS not_timely,
    round(100.0 * count(*) FILTER (WHERE timely_response = 'Yes') / count(*), 2) AS timely_pct
FROM complaints
WHERE timely_response IN ('Yes', 'No')
GROUP BY issuer, year
ORDER BY issuer, year;
