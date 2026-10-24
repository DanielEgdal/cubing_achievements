from datetime import date


def rows(conn, query, params=None):
    cursor = conn.execute(query, params or [])
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def achievement_options(conn):
    return rows(conn, 'SELECT achievement_id, name, category FROM achievements ORDER BY name')


def earned_achievements(conn, category='', achievement_id='', status='all', page=1, per_page=50):
    conditions = []
    params = []
    if category:
        conditions.append('a.category = ?')
        params.append(category)
    if achievement_id:
        conditions.append('a.achievement_id = ?')
        params.append(achievement_id)
    if status == 'unawarded':
        conditions.append('ca.date_awarded IS NULL')
    elif status == 'awarded':
        conditions.append('ca.date_awarded IS NOT NULL')
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    source = """
        FROM competitor_achievements ca
        JOIN achievements a USING (achievement_id)
        JOIN competitors c USING (wca_id)
    """
    total = conn.execute('SELECT count(*) ' + source + where, params).fetchone()[0]
    page = min(page, max(1, (total + per_page - 1) // per_page))
    entries = rows(conn, """
        SELECT ca.*, a.name AS achievement_name, a.category, c.name, c.nationality
    """ + source + where + """
        ORDER BY ca.date_achieved DESC NULLS LAST, ca.achievement_id, ca.wca_id
        LIMIT ? OFFSET ?
    """, [*params, per_page, (page - 1) * per_page])
    return entries, total, page


def competitors(conn, search='', page=1, per_page=50):
    where = ' WHERE wca_id ILIKE ? OR name ILIKE ?' if search else ''
    params = [f'%{search}%', f'%{search}%'] if search else []
    total = conn.execute('SELECT count(*) FROM competitors' + where, params).fetchone()[0]
    page = min(page, max(1, (total + per_page - 1) // per_page))
    entries = rows(conn, 'SELECT * FROM competitors' + where +
                   ' ORDER BY name, wca_id LIMIT ? OFFSET ?',
                   [*params, per_page, (page - 1) * per_page])
    return entries, total, page


def profile(conn, wca_id):
    people = rows(conn, 'SELECT * FROM competitors WHERE wca_id = ?', [wca_id])
    if not people:
        return None, []
    entries = rows(conn, """
        SELECT ca.*, a.name AS achievement_name, a.category
        FROM competitor_achievements ca JOIN achievements a USING (achievement_id)
        WHERE ca.wca_id = ?
        ORDER BY ca.date_achieved DESC NULLS LAST, ca.achievement_id
    """, [wca_id])
    return people[0], entries


def certificate(conn, wca_id, achievement_id):
    entries = rows(conn, """
        SELECT ca.*, c.name, a.name AS achievement_name, a.category
        FROM competitor_achievements ca
        JOIN competitors c USING (wca_id)
        JOIN achievements a USING (achievement_id)
        WHERE ca.wca_id = ? AND ca.achievement_id = ?
    """, [wca_id, achievement_id])
    return entries[0] if entries else None


def mark_awarded(conn, wca_id, achievement_id):
    updated = conn.execute("""
        UPDATE competitor_achievements SET date_awarded = ?
        WHERE wca_id = ? AND achievement_id = ? AND date_awarded IS NULL
        RETURNING date_awarded
    """, [date.today(), wca_id, achievement_id]).fetchone()
    if updated:
        return 'awarded'
    if certificate(conn, wca_id, achievement_id) is not None:
        return 'already_awarded'
    return 'not_found'
