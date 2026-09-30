-- Monthly keyword mentions in narratives, for the event study. The CFPB does not record
-- the card product, so the narrative text is the only way to see which card a complaint
-- is about. Counts are of complaints with a narrative, through July 2026.
WITH flagged AS (
    SELECT
        issuer,
        month,
        regexp_matches(narrative, '(?i)annual\s+(membership\s+)?fee|membership\s+fee') AS annual_fee,
        regexp_matches(narrative, '(?i)\bplatinum\b') AS platinum,
        regexp_matches(narrative, '(?i)sapphire\s+reserved?\b') AS sapphire_reserve,
        regexp_matches(narrative, '(?i)statement\s+credits?') AS statement_credit,
        regexp_matches(narrative, '(?i)\blounges?\b') AS lounge
    FROM complaints
    WHERE has_narrative AND month <= DATE '2026-07-01'
)
SELECT
    issuer,
    month,
    count(*) AS narratives,
    count(*) FILTER (WHERE annual_fee) AS mentions_annual_fee,
    count(*) FILTER (WHERE platinum) AS mentions_platinum,
    count(*) FILTER (WHERE sapphire_reserve) AS mentions_sapphire_reserve,
    count(*) FILTER (WHERE statement_credit) AS mentions_statement_credit,
    count(*) FILTER (WHERE lounge) AS mentions_lounge,
    count(*) FILTER (WHERE platinum AND annual_fee) AS mentions_platinum_and_annual_fee,
    count(*) FILTER (WHERE sapphire_reserve AND annual_fee) AS mentions_sapphire_reserve_and_annual_fee
FROM flagged
GROUP BY issuer, month
ORDER BY issuer, month;
