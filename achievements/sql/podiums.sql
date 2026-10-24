-- Params: $podium_count

SELECT
    r.person_id AS wca_id,
    c.name AS competition,
    make_date(c.year, c.month, c.day) AS date_achieved
FROM wca.results r
JOIN wca.competitions c ON c.id = r.competition_id
WHERE r.round_type_id in ('c', 'f')
    AND r.best > 0
    AND r.pos in (1, 2, 3)
QUALIFY row_number() OVER (PARTITION BY wca_id ORDER BY date_achieved) = $podium_count