import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import duckdb

from database import ROOT, WCA_DB_FILE

export_dir = ROOT / 'WCA_export'
db_file = WCA_DB_FILE
prefix = 'WCA_export_'


def load_table(conn, table, file):
    csv_options = "delim = '\t', header = true, quote = '', nullstr = ['null']"

    # Infer schema. Specify event_id manually due to incorrect type inference
    escaped_file = str(file).replace("'", "''")
    columns = [row[0] for row in conn.sql(f"DESCRIBE SELECT * FROM read_csv('{escaped_file}', {csv_options})").fetchall()]
    if 'event_id' in columns:
        csv_options += ", types = {event_id: 'varchar'}"

    conn.sql(f"""
            CREATE OR REPLACE TABLE {table} AS
            SELECT
                *
            FROM
                read_csv('{escaped_file}', {csv_options})
        """)


def build_database(source_dir=export_dir, target_file=db_file, report=print):
    source_dir = Path(source_dir)
    target_file = Path(target_file)
    target_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = target_file.with_name(target_file.stem + '_tmp.duckdb')
    if temporary_file.exists():
        temporary_file.unlink()
    conn = duckdb.connect(str(temporary_file))
    try:
        for filename in sorted(source_dir.glob(f'{prefix}*.tsv')):
            table = filename.stem[len(prefix):]
            if not table.replace('_', '').isalnum():
                raise ValueError(f'Invalid export table name: {table}')
            report(f"starting table {table}")
            start = time.perf_counter()
            load_table(conn, table, filename)
            rows = conn.execute(f'SELECT count(*) FROM "{table}"').fetchall()[0][0]
            report(f"{table}: {rows:,} rows in {time.perf_counter() - start:.2f}s")

        with open(source_dir / 'metadata.json', encoding='utf-8') as f:
            metadata = json.load(f)
        # Export timestamps remain naive UTC for the existing incremental checks.
        export_date = datetime.strptime(
            metadata['export_date'].removesuffix(' UTC'), '%Y-%m-%d %H:%M:%S')
        loaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
        conn.execute("""
            CREATE TABLE export_metadata (
                export_format_version VARCHAR,
                version_label VARCHAR,
                export_date TIMESTAMP,
                loaded_at TIMESTAMP
            )
        """)
        conn.execute('INSERT INTO export_metadata VALUES (?, ?, ?, ?)',
                     [metadata['export_format_version'], metadata['version_label'],
                      export_date, loaded_at])
        report(f"export_metadata: export_date={export_date}, loaded_at={loaded_at}")
    finally: # Always close the connection
        conn.close()
    os.replace(temporary_file, target_file)
    report('Done!')


if __name__ == '__main__':
    build_database()
