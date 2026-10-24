import database
from achievement_runner import load_achievements, run_achievement
from competitors import populate_competitors
# True: run every achievement. False: only run those not run since the last database update.
RUN_ALL = False


def main(run_all=RUN_ALL, db_file=database.ACHIEVEMENTS_DB_FILE,
         wca_file=database.WCA_DB_FILE, report=print):
    database.initialize(db_file)
    achievements = load_achievements()
    with database.connection(db_file, wca_file) as conn:
        report(f"competitors: {populate_competitors(conn):,}")
        export_date, loaded_at = database.export_info(conn)
        report(f"WCA export date: {export_date}")
        for achievement in achievements:
            run_achievement(conn, achievement, export_date, loaded_at,
                            run_all=run_all, report=report)
    report('Done!')


if __name__ == '__main__':
    main()
