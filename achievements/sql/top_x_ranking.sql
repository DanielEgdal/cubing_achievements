-- First date a competitor was top $ranking in the world for $event_id.
-- Params: $event_id, $ranking (e.g. 100), $result_type ('single' or 'average')

WITH valid AS (
    SELECT
        r.person_id,
        make_date(c.year, c.month, c.day) AS comp_date,
        c.name AS competition,
        CASE WHEN $result_type = 'average' THEN r.average ELSE r.best END AS result
    FROM wca.results r
    JOIN wca.competitions c ON c.id = r.competition_id
    WHERE r.event_id = $event_id
        AND (CASE WHEN $result_type = 'average' THEN r.average ELSE r.best END) > 0
),

-- Best result per person per date (collapses multiple rounds on one day).
daily AS (
    SELECT person_id, comp_date, min(result) AS result, min_by(competition, result) AS competition
    FROM valid
    GROUP BY person_id, comp_date
),

-- Get from daily results to PRs and their previous PRs.
pr_progression AS (
    SELECT person_id, comp_date, pr, prev_pr, competition
    FROM (
        SELECT
            person_id,
            comp_date,
            min_by(competition, result) OVER w AS competition,
            min(result) OVER w AS pr,
            -- No earlier result means no PR yet, i.e. an infinitely slow previous PR.
            coalesce(min(result) OVER (w ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
                     'infinity'::DOUBLE) AS prev_pr
        FROM daily
        WINDOW w AS (PARTITION BY person_id ORDER BY comp_date)
    )
    WHERE pr < prev_pr -- Only include the days where you beat your PR
),

danes AS (
    SELECT p.*
    FROM pr_progression p
    SEMI JOIN competitors c ON c.wca_id = p.person_id -- Narrow the scope only to competitors we are tracking
),

ranked AS (
    SELECT
        d.person_id,
        d.comp_date,
        d.competition,
        1 + count(other.person_id) AS world_rank
    FROM danes as d
    LEFT JOIN pr_progression other
        ON other.pr < d.pr
        AND other.prev_pr >= d.pr -- Reduce join size, only count the one result. Also skips distinct count
        AND other.comp_date <= d.comp_date
    GROUP BY d.person_id, d.comp_date, d.competition
)

SELECT
    person_id AS wca_id,
    min_by(competition, comp_date) AS competition,
    min(comp_date) AS date_achieved
FROM ranked
WHERE world_rank <= $ranking
GROUP BY person_id