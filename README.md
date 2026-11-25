# Cubing achievements

Python/DuckDB achievement calculations with a Danish Flask website.
Backend identifiers, comments, and technical logs are English; the UI and
certificates are Danish.

## Run the website

From the command line in this project:

```sh
python -m pip install -r requirements.txt
python webapp.py
```

Open <http://127.0.0.1:8000>. The default server uses Waitress, one process,
and loopback binding. No Node.js or frontend build is needed.
Paths resolve relative to the project directory.
DuckDB files live in `databases`; the directory is created automatically when
initializing or building a database. Export downloads remain in `WCA_export`.

### Pages

- **Oversigt:** earned achievements with category and achievement dropdowns.
- **Deltagere:** search by name or WCA ID, then open a person's profile.
- Overview, administration, and profiles show `achieved_at_competition` as the
  competition name, or "Ikke angivet" when it is missing. Certificates include
  the competition beneath the achieved date when available.
- **Administration → Tilføj deltagere:** track a non-Danish competitor from
  the local export. Danes are included automatically when the pipeline runs.
  New competitors' achievements appear after the next calculation.
- **Administration → Overrækkelser:** newest achieved dates first, with award
  status filtering. **Markér overrakt** records today's date once; repeated
  submissions preserve the original date.
- **Generér diplom:** opens a certificate independently of awarding.
  **Udskriv / Gem som PDF** opens the browser print dialog. Choose Save as PDF,
  A4 landscape, and turn off browser headers/footers. The certificate date
  is always the stored `date_achieved`, not the award or print date.
- **Administration → Drift:** run the existing Windows export batch file
  followed by the DuckDB builder, or calculate achievements separately.
  Calculations are incremental unless **Gennemtving alle beregninger** is checked.

`date_achieved` and `date_awarded` remain SQL DATE columns. Display formatting
does not apply timezone conversion.

## Jobs and database access

Only one background job runs at a time. Browsing requests can run concurrently,
including while a refresh downloads the export and builds a temporary database.
The final WCA file replacement blocks new database requests and waits for active
requests to close their connections. Achievement calculation remains exclusive
for its entire run. During these exclusive phases, database-dependent pages and
edits return a temporary-unavailability message. Admin edits are serialized;
overlapping edits also receive that message, without blocking browsing.
The status page remains available with the last 100 lines of technical output.
Coordination is within one application process only. Do not run command-line
maintenance or multiple server processes against these files concurrently.

The update button calls `scripts/win_download_export.bat` on Windows or
`scripts/download_export.sh` on other platforms. These scripts own
download and extraction into `WCA_export`.

Each achievement calculation is transactional. Previously completed achievements
remain committed if a later achievement fails. Existing award dates are preserved
on matched results, while the existing merge still removes results that no longer
qualify.

To run the general process locally without the UI, run the following three commands:

```powershell
.\scripts\win_download_export.bat
python build_duckdb.py
python run_achievements.py
```

On Unix, use `sh scripts/download_export.sh` for the download step. Both download
scripts resolve the project root from their own location.

## Structure and future hosting

- `database.py`: shared paths, connection lifetime, and existing schema setup.
- `databases/`: local `wca.duckdb`, `achievements.duckdb`, and temporary database
  files (ignored by Git).
- `scripts/`: Windows and Unix export download scripts.
- `competitors.py`, `achievement_runner.py`, `build_duckdb.py`: backend operations.
- `web_queries.py`: website queries and award updates.
- `admin_jobs.py`: background execution and exclusive maintenance access.
- `webapp.py`: Flask factory, routes, and Danish display labels.
- `templates` / `static`: Jinja pages, plain CSS, and small progressive enhancements.

Achievement names and categories come from the `name` and `category` fields in
`achievements/achievements.yaml`. Edit them there, then run the achievement
calculation to synchronize them to the database. Both are updated even when the
calculation itself is skipped as up to date. Pages, dropdowns, and certificates
use the stored values; no separate name or category label maps are needed.

## Disclaimer

AI was very heavily used to generate the initial front end. Including this README file with documentation.