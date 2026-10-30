"""Read-only aggregate host pressure and identity-bound own descendants; no argv."""
import json
import os
from pathlib import Path
import threading
import time


class HostSamples:
    def __init__(self):
        self.stopped = threading.Event()
        self.rows = []
        self.thread = threading.Thread(target=self._run, name='w11-host-sampler')

    def start(self):
        self.thread.start()

    def _run(self):
        import psutil
        root = psutil.Process()
        while not self.stopped.is_set():
            row = {'at': time.monotonic(), 'logical_cpus': os.cpu_count(), 'processes': [], 'errors': []}
            try:
                for process in [root, *root.children(recursive=True)]:
                    try:
                        cpu = process.cpu_times()
                        row['processes'].append({'pid': process.pid, 'ppid': process.ppid(), 'name': process.name(),
                            'created_at': process.create_time(), 'user_seconds': cpu.user, 'system_seconds': cpu.system,
                            'threads': process.num_threads(), 'rss': process.memory_info().rss})
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
                        row['errors'].append(type(error).__name__)
                for name, path in [('cpu_ticks', '/proc/stat'), ('cpu_psi', '/proc/pressure/cpu'),
                                   ('io_psi', '/proc/pressure/io'), ('memory_psi', '/proc/pressure/memory'),
                                   ('memory', '/proc/meminfo'), ('swap_activity', '/proc/vmstat'), ('load', '/proc/loadavg')]:
                    lines = Path(path).read_text().splitlines()
                    if name == 'cpu_ticks':
                        lines = [line for line in lines if line.startswith('cpu ')]
                    if name == 'swap_activity':
                        lines = [line for line in lines if line.startswith(('pswpin ', 'pswpout '))]
                    row[name] = lines
            except (OSError, psutil.Error) as error:
                row['errors'].append(type(error).__name__)
            self.rows.append(row)
            self.stopped.wait(1.)

    def close(self, destination):
        self.stopped.set()
        self.thread.join(3)
        if self.thread.is_alive():
            raise RuntimeError('host-sampler-survived')
        Path(destination).write_text(json.dumps({'rows': self.rows,
            'scope': 'Own live process identities only; departed CPU accounting may be incomplete. Canonical queue health determines external contention.',
            'owner_process_inspected': False}, separators=(',', ':')) + '\n')
