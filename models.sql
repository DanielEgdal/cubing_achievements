CREATE TABLE IF NOT EXISTS competitors (
    wca_id VARCHAR PRIMARY KEY,
    name VARCHAR,
    nationality VARCHAR
);

CREATE TABLE IF NOT EXISTS non_danes_to_track (
    wca_id VARCHAR PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS achievements (
    achievement_id VARCHAR PRIMARY KEY,
    name VARCHAR,
    category VARCHAR,
    event_id VARCHAR,
    last_run_at TIMESTAMP,
    last_run_export_date TIMESTAMP,
    sql_hash VARCHAR
);

CREATE TABLE IF NOT EXISTS competitor_achievements (
    achievement_id VARCHAR REFERENCES achievements(achievement_id),
    wca_id VARCHAR REFERENCES competitors(wca_id),
    date_achieved DATE,
    achieved_at_competition VARCHAR,
    date_awarded DATE,
    PRIMARY KEY (achievement_id, wca_id)
);