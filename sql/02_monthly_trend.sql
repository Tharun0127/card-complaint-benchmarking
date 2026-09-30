-- Monthly complaint volume by issuer, with each issuer's share of all credit card
-- complaints in the CFPB database that month and an index against its own 2023 average.
WITH monthly AS (
    SELECT issuer, month, count(*) AS complaints
    FROM complaints
    GROUP BY issuer, month
),
market AS (
    SELECT month, count(*) AS all_card_complaints
    FROM cards_all
    GROUP BY month
),
base AS (
    SELECT issuer, avg(complaints) AS avg_2023
    FROM monthly
    WHERE year(month) = 2023
    GROUP BY issuer
)
SELECT
    m.issuer,
    m.month,
    m.complaints,
    round(100.0 * m.complaints / k.all_card_complaints, 2) AS share_of_all_card_complaints_pct,
    round(100.0 * m.complaints / b.avg_2023, 1) AS index_vs_2023_avg,
    round(avg(m.complaints) OVER (
        PARTITION BY m.issuer ORDER BY m.month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ), 1) AS complaints_3m_avg
FROM monthly m
JOIN market k USING (month)
JOIN base b USING (issuer)
ORDER BY m.issuer, m.month;
