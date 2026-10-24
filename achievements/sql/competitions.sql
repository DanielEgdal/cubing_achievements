-- Params: $competition_count
WITH CTE AS (
SELECT DISTINCT
    r.person_id AS wca_id,
    c.name AS competition,
    make_date(c.year, c.month, c.day) AS date_achieved
FROM wca.results r
JOIN wca.competitions c ON c.id = r.competition_id
)

SELECT
    wca_id,
    competition,
    date_achieved
FROM CTE
QUALIFY row_number() OVER (PARTITION BY wca_id ORDER BY date_achieved) = $competition_count