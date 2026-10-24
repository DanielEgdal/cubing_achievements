import re


class TrackingError(ValueError):
    pass


def populate_competitors(conn):
    """Upsert everyone currently Danish, plus the manually tracked non-Danes."""
    # sub_id = 1 is the person's current name/country in the WCA export.
    new_competitors = conn.execute("""
        SELECT count(*) FROM wca.persons
        WHERE sub_id = 1
            AND (country_id = 'Denmark'
                 OR wca_id IN (SELECT wca_id FROM non_danes_to_track))
            AND wca_id NOT IN (SELECT wca_id FROM competitors)
    """).fetchone()[0]
    conn.execute("""
            INSERT INTO competitors (wca_id, name, nationality)
            SELECT wca_id, name, country_id
            FROM wca.persons
            WHERE sub_id = 1
                AND (country_id = 'Denmark'
                     OR wca_id IN (SELECT wca_id FROM non_danes_to_track))
            ON CONFLICT (wca_id) DO UPDATE SET
                name = excluded.name,
                nationality = excluded.nationality
        """)
    if new_competitors:
        conn.execute('UPDATE achievements SET last_run_at = NULL')
    return conn.execute('SELECT count(*) FROM competitors').fetchone()[0]


def add_non_danes_to_track(conn, wca_ids):
    normalized_ids = [wca_id.strip().upper() for wca_id in wca_ids]
    conn.execute('BEGIN TRANSACTION')
    try:
        for wca_id in normalized_ids:
            if not re.fullmatch(r'[0-9]{4}[A-Z]{4}[0-9]{2}', wca_id):
                raise TrackingError('invalid_id')
            person = conn.execute(
                'SELECT country_id FROM wca.persons WHERE sub_id = 1 AND wca_id = ?',
                [wca_id]).fetchone()
            if person is None:
                raise TrackingError('unknown_id')
            if person[0] == 'Denmark' or conn.execute(
                'SELECT 1 FROM competitors WHERE wca_id = ?', [wca_id]).fetchone():
                raise TrackingError('already_tracked')
            if conn.execute('SELECT 1 FROM non_danes_to_track WHERE wca_id = ?',
                            [wca_id]).fetchone():
                raise TrackingError('already_tracked')
            conn.execute('INSERT INTO non_danes_to_track VALUES (?)', [wca_id])
        populate_competitors(conn)
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise
    return normalized_ids