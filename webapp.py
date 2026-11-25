"""Local achievements website. Run with: python webapp.py"""
import hmac
import os
import secrets
from pathlib import Path

import duckdb
from flask import (
    Blueprint, Flask, abort, current_app, flash, g, jsonify,
    redirect, render_template, request, session, url_for,
)

import database
import web_queries
from admin_jobs import JobManager, refresh_wca
from competitors import TrackingError, add_non_danes_to_track
from run_achievements import main as run_achievements

admin = Blueprint('admin', __name__, url_prefix='/admin')

STATUS_LABELS = {
    'idle': 'Ingen kørsel endnu', 'running': 'Kører', 'succeeded': 'Gennemført',
    'failed': 'Mislykket', 'interrupted': 'Afbrudt ved genstart',
}
TRACKING_MESSAGES = {
    'invalid_id': 'Ugyldigt WCA-id. Brug fx 2010ABCD01.',
    'unknown_id': 'WCA-id findes ikke i det lokale eksportdatasæt. Opdater WCA-data.',
    'already_tracked': 'Deltageren følges allerede. Danske deltagere medtages automatisk.',
}


def get_jobs():
    return current_app.extensions['jobs']


def page_number():
    try:
        return max(1, int(request.args.get('page', '1')))
    except ValueError:
        abort(400, description='Ugyldigt sidetal.')


def get_connection(wca=False):
    if not g.get('database_gate'):
        abort(503, description='Databasen er optaget. Prøv igen om lidt.')
    if 'connection' not in g:
        context = database.connection(
            current_app.config['DATABASE'],
            current_app.config['WCA_DATABASE'] if wca else None)
        g.connection = context.__enter__()
        g.connection_context = context
    return g.connection


def filtered_achievements():
    conn = get_connection()
    options = web_queries.achievement_options(conn)
    category = request.args.get('category', '')
    achievement_id = request.args.get('achievement', '')
    status = request.args.get('status', 'all')
    if status not in {'all', 'unawarded', 'awarded'}:
        abort(400, description='Ugyldigt filter.')
    categories = sorted({entry['category'] for entry in options if entry['category']})
    if category and category not in categories:
        abort(400, description='Ukendt kategori.')
    choices = [entry for entry in options if not category or entry['category'] == category]
    if achievement_id and not any(
            entry['achievement_id'] == achievement_id for entry in options):
        abort(400, description='Ukendt bedrift.')
    if achievement_id and not any(
            entry['achievement_id'] == achievement_id for entry in choices):
        achievement_id = ''
    entries, total, page = web_queries.earned_achievements(
        conn, category, achievement_id, status, page_number())
    return dict(entries=entries, total=total, page=page, pages=max(1, (total + 49) // 50),
                categories=categories, choices=choices, category=category,
                selected_achievement=achievement_id, status=status)


@admin.route('/competitors', methods=['GET', 'POST'])
def competitors_admin():
    conn = get_connection(wca=True)
    if request.method == 'POST':
        try:
            identifiers = add_non_danes_to_track(conn, [request.form.get('wca_id', '')])
        except TrackingError as error:
            flash(TRACKING_MESSAGES[str(error)], 'error')
        else:
            flash(f'{identifiers[0]} følges nu. Beregn bedrifter fra driftssiden '
                  'for at opdatere deltagerens profil.', 'success')
        return redirect(url_for('admin.competitors_admin'), code=303)
    entries = web_queries.rows(conn, """
        SELECT t.wca_id, c.name, c.nationality
        FROM non_danes_to_track t LEFT JOIN competitors c USING (wca_id)
        ORDER BY c.name, t.wca_id
    """)
    return render_template('admin_competitors.html', entries=entries)


@admin.get('/achievements')
def achievements_admin():
    return render_template('achievements.html', administration=True, **filtered_achievements())


@admin.post('/award/<wca_id>/<achievement_id>')
def award(wca_id, achievement_id):
    result = web_queries.mark_awarded(get_connection(), wca_id, achievement_id)
    if result == 'not_found':
        abort(404)
    flash('Markeret som overrakt.' if result == 'awarded' else
          'Allerede overrakt. Den oprindelige dato er bevaret.', 'success')
    return redirect(url_for('admin.achievements_admin',
                            status=request.form.get('status', 'all'),
                            category=request.form.get('category', ''),
                            achievement=request.form.get('achievement', ''),
                            page=request.form.get('page', '1')), code=303)


@admin.get('/certificate/<wca_id>/<achievement_id>')
def certificate(wca_id, achievement_id):
    entry = web_queries.certificate(get_connection(), wca_id, achievement_id)
    if entry is None:
        abort(404)
    return render_template('certificate.html', entry=entry)


@admin.route('/runs', methods=['GET', 'POST'])
def runs():
    """Show job status on GET; start the requested background job on POST.

    Each lambda wraps a function and its arguments for the job manager to call
    later, accepting the progress-reporting function supplied by the manager.
    """
    if request.method == 'POST':
        operation = request.form.get('operation')
        if operation == 'refresh':
            target = current_app.config['WCA_DATABASE']
            replacement_guard = get_jobs().exclusive_database()
            job_function = lambda report: refresh_wca(
                target, report, replacement_guard=replacement_guard)
        elif operation == 'calculate':
            force = request.form.get('force_all') == 'on'
            db_file = current_app.config['DATABASE']
            wca_file = current_app.config['WCA_DATABASE']
            job_function = lambda report: run_achievements(force, db_file, wca_file, report)
        else:
            abort(400, description='Ukendt handling.')
        job_started = get_jobs().start(
            operation, job_function, exclusive=operation != 'refresh')
        if not job_started:
            flash('En kørsel er allerede i gang.', 'error')
        return redirect(url_for('admin.runs'), code=303)
    return render_template('runs.html', job=get_jobs().snapshot())


@admin.get('/runs/status')
def run_status():
    job = get_jobs().snapshot()
    job['label'] = STATUS_LABELS[job['status']]
    return jsonify(job)


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=database.ACHIEVEMENTS_DB_FILE,
        WCA_DATABASE=database.WCA_DB_FILE,
        RUNTIME_DIR=database.ROOT / '.runtime',
        SECRET_KEY=os.environ.get('ACHIEVEMENTS_SECRET_KEY'),
        MAX_CONTENT_LENGTH=16 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Strict',
    )
    if config:
        app.config.update(config)
    runtime = Path(app.config['RUNTIME_DIR'])
    runtime.mkdir(parents=True, exist_ok=True)
    if not app.config['SECRET_KEY']:
        secret_file = runtime / 'secret'
        if not secret_file.exists():
            secret_file.write_text(secrets.token_hex(32), encoding='ascii')
        app.config['SECRET_KEY'] = secret_file.read_text(encoding='ascii')
    jobs = JobManager(runtime / 'job.json')
    app.extensions['jobs'] = jobs
    database.initialize(app.config['DATABASE'])
    app.register_blueprint(admin)

    @app.before_request
    def prepare_request():
        if request.method == 'POST':
            token = request.form.get('csrf_token', '')
            if not token or not hmac.compare_digest(
                    token.encode('utf-8'), session.get('csrf_token', '').encode('utf-8')):
                abort(400, description='Formularen er udløbet. Genindlæs siden og prøv igen.')
        independent = {'admin.runs', 'admin.run_status', 'static', None}
        if request.endpoint not in independent:
            if not jobs.enter_database(write=request.method == 'POST'):
                abort(503, description='Databasen er optaget. Se driftssiden, og prøv igen senere.')
            g.database_gate = True

    @app.teardown_request
    def close_connection(error):
        try:
            context = g.pop('connection_context', None)
            if context is not None:
                context.__exit__(None, None, None)
        finally:
            if g.pop('database_gate', False):
                jobs.leave_database(write=request.method == 'POST')

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
        return response

    @app.context_processor
    def template_helpers():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)

        def page_url(number):
            arguments = request.args.to_dict()
            arguments['page'] = number
            return url_for(request.endpoint, **arguments)

        return dict(
            csrf_token=session['csrf_token'], page_url=page_url,
            status_labels=STATUS_LABELS,
        )

    @app.template_filter('danish_date')
    def danish_date(value):
        return value.strftime('%d.%m.%Y') if value is not None else 'Ukendt dato'

    @app.get('/')
    def overview():
        return render_template('achievements.html', administration=False, **filtered_achievements())

    @app.get('/competitors')
    def competitors_page():
        search = request.args.get('search', '').strip()
        entries, total, page = web_queries.competitors(get_connection(), search, page_number())
        return render_template('competitors.html', entries=entries, total=total,
                               page=page, pages=max(1, (total + 49) // 50), search=search)

    @app.get('/competitors/<wca_id>')
    def profile(wca_id):
        person, entries = web_queries.profile(get_connection(), wca_id.upper())
        if person is None:
            abort(404)
        return render_template('profile.html', person=person, entries=entries)

    @app.errorhandler(duckdb.Error)
    @app.errorhandler(OSError)
    def database_error(error):
        app.logger.exception('Database or filesystem operation failed')
        return render_template('error.html', title='Data er ikke tilgængelige',
                               message='Handlingen kunne ikke gennemføres. Kontrollér WCA-data '
                               'og undgå at køre kommandolinjejob samtidig med hjemmesiden. '
                               'Tekniske detaljer findes i serverloggen.'), 503

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(503)
    def http_error(error):
        messages = {400: 'Ugyldig forespørgsel', 404: 'Siden findes ikke',
                    413: 'Formularen er for stor', 503: 'Databasen er optaget'}
        return render_template('error.html', title=messages[error.code],
                               message=error.description if error.code in {400, 503}
                               else 'Gå tilbage til oversigten og prøv igen.'), error.code

    return app


def main():
    from waitress import create_server

    server = create_server(create_app(), host='127.0.0.1', port=8000, threads=4)
    try:
        print(f'Serving on http://{server.effective_host}:{server.effective_port}', flush=True)
        server.run()
    finally:
        server.close()


if __name__ == '__main__':
    main()
