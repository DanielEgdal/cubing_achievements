import json
import logging
import os
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path

from build_duckdb import build_database
from database import ROOT

logger = logging.getLogger(__name__)


def refresh_wca(target_file, report=print, replacement_guard=None):
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
    build_database(ROOT / 'WCA_export', target_file, report,
                   replacement_guard=replacement_guard)
    report('WCA data updated. Run achievement calculation next.')


class JobManager:
    """Run one database maintenance job at a time and track its status for the admin page.

    Follows a monitor-style design: shared job state and the methods accessing it
    are grouped together, with status_lock protecting concurrent access.
    Database requests may overlap. Exclusive maintenance blocks new requests
    and waits for active requests to close their connections.
    """

    def __init__(self, state_file):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        # The worker updates status while web requests read it.
        self.status_lock = threading.RLock()
        self.database_condition = threading.Condition(self.status_lock)
        self.active_requests = 0
        self.database_busy = False
        self.database_writer = False
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

    def enter_database(self, write=False):
        with self.status_lock:
            if self.database_busy or (write and self.database_writer):
                return False
            self.active_requests += 1
            if write:
                self.database_writer = True
            return True

    def leave_database(self, write=False):
        with self.database_condition:
            self.active_requests -= 1
            if write:
                self.database_writer = False
            self.database_condition.notify_all()

    @contextmanager
    def exclusive_database(self):
        with self.database_condition:
            self.database_condition.wait_for(lambda: not self.database_busy)
            self.database_busy = True
        try:
            with self.database_condition:
                self.database_condition.wait_for(lambda: self.active_requests == 0)
            yield
        finally:
            with self.database_condition:
                self.database_busy = False
                self.database_condition.notify_all()

    def start(self, operation, job_function, exclusive=True):
        with self.status_lock:
            if self.state['status'] == 'running':
                return False
            self.state = {'status': 'running', 'operation': operation,
                          'output': [], 'error': None}
            self._save_job_state_to_file()
            self.thread = threading.Thread(
                target=self._run_job, args=(job_function, exclusive), daemon=True)
            self.thread.start()
            return True

    def report(self, message):
        with self.status_lock:
            self.state['output'].append(str(message))
            self.state['output'] = self.state['output'][-100:]

    def _run_job(self, job_function, exclusive):
        try:
            if exclusive:
                with self.exclusive_database():
                    job_function(self.report)
            else:
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
