-- Params: $podium_count

WITH CTE AS (
SELECT
    r.person_id AS wca_id,
    make_date(c.year, c.month, c.day) AS date_achieved,
    c.name AS competition,
    row_number() OVER (PARTITION BY c.id, r.event_id ORDER BY pos) AS danish_ranking
FROM wca.results r
JOIN wca.competitions c ON c.id = r.competition_id
JOIN wca.championships ch ON ch.competition_id = c.id
WHERE ch.championship_type = 'DK'
    AND r.person_country_id = 'Denmark'
    AND r.round_type_id in ('c', 'f')
    AND r.best > 0
)

SELECT
    wca_id,
    competition,
    date_achieved
FROM CTE
WHERE danish_ranking <= 3
QUALIFY row_number() OVER (PARTITION BY wca_id ORDER BY date_achieved) = $podium_count
