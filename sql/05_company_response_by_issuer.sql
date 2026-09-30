-- How each issuer closed its complaints. Complaints still "In progress" are excluded
-- because they have no outcome yet and are concentrated in the last two months.
SELECT
    issuer,
    count(*) AS closed_complaints,
    round(100.0 * count(*) FILTER (WHERE company_response = 'Closed with monetary relief') / count(*), 1)
        AS monetary_relief_pct,
    round(100.0 * count(*) FILTER (WHERE company_response = 'Closed with non-monetary relief') / count(*), 1)
        AS non_monetary_relief_pct,
    round(100.0 * count(*) FILTER (WHERE company_response = 'Closed with explanation') / count(*), 1)
        AS explanation_only_pct,
    round(100.0 * count(*) FILTER (WHERE company_response = 'Untimely response') / count(*), 2)
        AS untimely_pct
FROM complaints
WHERE company_response <> 'In progress'
GROUP BY issuer
ORDER BY monetary_relief_pct DESC;
