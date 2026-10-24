-- Date of the competition where the person reached their 10th country.
-- Country ids starting with 'X' are multi-country (e.g. FMC Asia) and are skipped.
WITH first_visit AS (
    SELECT
        r.person_id,
        c.country_id,
        min_by(c.name, make_date(c.year, c.month, c.day)) AS competition,
        min(make_date(c.year, c.month, c.day)) AS first_date
    FROM wca.results r
    JOIN wca.competitions c ON c.id = r.competition_id
    WHERE c.country_id NOT LIKE 'X%'
    GROUP BY r.person_id, c.country_id
)
SELECT
    person_id AS wca_id,
    competition,
    first_date AS date_achieved
FROM first_visit
QUALIFY row_number() OVER (PARTITION BY person_id ORDER BY first_date) = 10