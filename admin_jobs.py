import json
import logging
import os
import subprocess
import threading
from pathlib import Path

from build_duckdb import build_database
from database import ROOT

logger = logging.getLogger(__name__)


def refresh_wca(target_file, report=print):
    if os.name == 'nt': # Windows
        script = Path('scripts') / 'win_download_export.bat'
        command = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', str(script)]
        failure_message = 'WCA export batch job failed; see output above.'
    else: # Linux
        script = ROOT / 'scripts' / 'download_export.sh'
        command = ['sh', str(script)]
        failure_message = 'WCA export shell job failed; see output above.'

    report(f'Running {script}')
    with subprocess.Popen(
            command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors='replace') as process:
        if process.stdout is not None:
            for line in process.stdout:
                report(line.rstrip())
        if process.wait() != 0:
            raise RuntimeError(failure_message)

    report('Building WCA database')
    build_database(ROOT / 'WCA_export', target_file, report)
    report('WCA data updated. Run achievement calculation next.')


class JobManager:
    """Run one database maintenance job at a time and track its status for the admin page.

    Follows a monitor-style design: shared job state and the methods accessing it
    are grouped together, with status_lock protecting concurrent access.
    database_lock separately prevents jobs and web requests from using the
    databases at the same time.
    """

    def __init__(self, state_file):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        # Web requests and background jobs must not use the databases at the same time.
        self.database_lock = threading.Lock()
        # The worker updates status while web requests read it.
        self.status_lock = threading.RLock()
        self.thread = None
        self.state = {'status': 'idle', 'operation': None, 'output': [], 'error': None}
        if self.state_file.exists():
            self.state = json.loads(self.state_file.read_text(encoding='utf-8'))
            if self.state['status'] == 'running':
                self.state.update(status='interrupted',
                                  error='Application stopped before the job completed.')
                self._save_job_state_to_file()

    def _save_job_state_to_file(self):
        temporary = self.state_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.state, ensure_ascii=True), encoding='utf-8')
        # Replace the status file only after the complete JSON has been written.
        temporary.replace(self.state_file)

    def snapshot(self):
        with self.status_lock:
            snapshot = self.state.copy()
            snapshot['output'] = self.state['output'].copy()
            return snapshot

    def enter_database(self):
        with self.status_lock:
            if self.state['status'] == 'running':
                return False
            return self.database_lock.acquire(blocking=False)

    def start(self, operation, job_function):
        with self.status_lock:
            if self.state['status'] == 'running':
                return False
            self.state = {'status': 'running', 'operation': operation,
                          'output': [], 'error': None}
            self._save_job_state_to_file()
            self.thread = threading.Thread(
                target=self._run_job, args=(job_function,), daemon=True)
            self.thread.start()
            return True

    def report(self, message):
        with self.status_lock:
            self.state['output'].append(str(message))
            self.state['output'] = self.state['output'][-100:]

    def _run_job(self, job_function):
        try:
            with self.database_lock:
                # The job calls report(...) to add progress messages to the admin page.
                job_function(self.report)
            with self.status_lock:
                self.state['status'] = 'succeeded'
                self._save_job_state_to_file()
        except Exception as error:
            logger.exception('Admin job failed')
            with self.status_lock:
                self.state.update(status='failed', error=str(error))
                try:
                    self._save_job_state_to_file()
                except OSError:
                    logger.exception('Could not persist failed job status')
