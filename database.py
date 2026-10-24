from contextlib import contextmanager
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
DATABASE_DIR = ROOT / 'databases'
WCA_DB_FILE = DATABASE_DIR / 'wca.duckdb'
ACHIEVEMENTS_DB_FILE = DATABASE_DIR / 'achievements.duckdb'
MODELS_FILE = ROOT / 'models.sql'


@contextmanager
def connection(db_file=ACHIEVEMENTS_DB_FILE, wca_file=None):
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_file))
    try:
        if wca_file is not None:
            if not Path(wca_file).is_file():
                raise FileNotFoundError('WCA database not found. Update WCA data first.')
            conn.execute('ATTACH ? AS wca (READ_ONLY)', [str(wca_file)])
        yield conn
    finally:
        conn.close()


def initialize(db_file=ACHIEVEMENTS_DB_FILE):
    with connection(db_file) as conn:
        conn.execute(MODELS_FILE.read_text(encoding='utf-8'))


def export_info(conn):
    return conn.execute('SELECT export_date, loaded_at FROM wca.export_metadata').fetchone()
