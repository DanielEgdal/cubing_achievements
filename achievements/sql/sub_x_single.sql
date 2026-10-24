-- Params: $event_id, $max_time (centiseconds, exclusive)
SELECT
    r.person_id AS wca_id,
    min_by(c.name, make_date(c.year, c.month, c.day)) AS competition,
    min(make_date(c.year, c.month, c.day)) AS date_achieved
FROM wca.results r
JOIN wca.competitions c ON c.id = r.competition_id
WHERE r.event_id = $event_id
    AND r.best > 0
    AND r.best < $max_time
GROUP BY r.person_id
