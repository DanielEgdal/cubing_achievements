import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

ACHIEVEMENTS_DIR = Path(__file__).resolve().parent / 'achievements'

MERGE_TEMPLATE = """
        MERGE INTO competitor_achievements t
        USING (
            SELECT $achievement_id AS achievement_id, q.wca_id, q.competition, q.date_achieved
            FROM ({query}) q
            SEMI JOIN competitors USING (wca_id)
        ) s
        ON t.achievement_id = s.achievement_id AND t.wca_id = s.wca_id
        WHEN MATCHED AND (t.date_achieved IS DISTINCT FROM s.date_achieved OR t.achieved_at_competition IS DISTINCT FROM s.competition) THEN
            UPDATE SET date_achieved = s.date_achieved, achieved_at_competition = s.competition
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (achievement_id, wca_id, achieved_at_competition, date_achieved)
            VALUES (s.achievement_id, s.wca_id, s.competition, s.date_achieved)
        WHEN NOT MATCHED BY SOURCE AND t.achievement_id = $achievement_id THEN
            DELETE
    """


def load_achievements():
    with open(ACHIEVEMENTS_DIR / 'achievements.yaml', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_query(achievement):
    with open(ACHIEVEMENTS_DIR / achievement['sql'], encoding='utf-8') as f:
        return f.read()


def sql_hash(achievement, query):
    # Hash covers the SQL text and the parameters, so a change to either triggers a re-run.
    params_json = json.dumps({'event_id': achievement.get('event_id'), **achievement.get('params', {})},
                             sort_keys=True)
    return hashlib.sha256((query + params_json).encode()).hexdigest()


def is_up_to_date(conn, achievement, query_hash, loaded_at):
    last_run, stored_hash = conn.execute(
        "SELECT last_run_at, sql_hash FROM achievements WHERE achievement_id = ?",
        [achievement['id']]).fetchone() or (None, None)
    # Compare to load time, not export date: a run between export and download used old data.
    up_to_date = last_run is not None and last_run > loaded_at and stored_hash == query_hash
    return up_to_date, last_run


def upsert_achievement(conn, achievement):
    conn.execute("""
            INSERT INTO achievements (achievement_id, name, category, event_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (achievement_id) DO UPDATE SET
                name = excluded.name,
                category = excluded.category,
                event_id = excluded.event_id
        """, [achievement['id'], achievement['name'], achievement['category'], achievement.get('event_id')])


def count_awarded(conn, achievement_id):
    return conn.execute("SELECT count(*) FROM competitor_achievements WHERE achievement_id = ?",
                        [achievement_id]).fetchone()[0]


def merge_results(conn, achievement, query):
    """Insert new rows, update changed dates (date_awarded untouched),
    and delete rows of this achievement that no longer qualify."""
    merge_sql = MERGE_TEMPLATE.replace('{query}', query)
    params = {'achievement_id': achievement['id'], 'event_id': achievement.get('event_id'),
              **achievement.get('params', {})}
    # DuckDB rejects unused named params, so only pass the ones referenced.
    params = {name: value for name, value in params.items() if f'${name}' in merge_sql}
    conn.execute(merge_sql, params)


def mark_run(conn, achievement, export_date, query_hash):
    conn.execute("""
            UPDATE achievements
            SET last_run_at = ?, last_run_export_date = ?, sql_hash = ?
            WHERE achievement_id = ?
        """, [datetime.now(timezone.utc).replace(tzinfo=None), export_date, query_hash, achievement['id']])


def _run_achievement(conn, achievement, export_date, loaded_at, run_all=False, report=print):
    query = load_query(achievement)
    query_hash = sql_hash(achievement, query)

    up_to_date, last_run = is_up_to_date(conn, achievement, query_hash, loaded_at)
    upsert_achievement(conn, achievement)
    if not run_all and up_to_date:
        report(f"Skipping achievement `{achievement['name']}`. (last run: {last_run})")
        return
    report(f"starting {achievement['name']}")

    start = time.perf_counter()
    before = count_awarded(conn, achievement['id'])
    merge_results(conn, achievement, query)
    after = count_awarded(conn, achievement['id'])
    elapsed = time.perf_counter() - start
    mark_run(conn, achievement, export_date, query_hash)

    report(f"{achievement['id']}: {after - before:,} new, {after:,} total in {elapsed:.2f}s")


def run_achievement(conn, achievement, export_date, loaded_at, run_all=False, report=print):
    conn.execute('BEGIN TRANSACTION')
    try:
        _run_achievement(conn, achievement, export_date, loaded_at, run_all, report)
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise
