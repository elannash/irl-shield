"""Small per-host performance queue; Python standard library plus system Perl.

No SDK, model, dataset, media or network dependency is introduced. Existing
benchmark licenses remain with their commands/artifacts; media stays benchmark-only.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import ctypes
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORAGE = ROOT / '.tmp/perf-queue'
PERF_LOCK = Path('/tmp/agents/irl-shield/perf.lock')
FORCE_AT = datetime(2026, 10, 30, 15, tzinfo=timezone.utc).timestamp()
HARD_STOP = datetime(2026, 10, 30, 16, tzinfo=timezone.utc).timestamp()
HOSTS = ('mac', 'linux')


def mac_idle(text):
    values = re.findall(r'CPU usage:[^\n]*?([0-9.]+)% idle', text)
    if len(values) != 2:
        raise ValueError('Mac readiness requires both top samples')
    idle = float(values[1])
    if not 0 <= idle <= 100:
        raise ValueError('Invalid Mac idle percentage')
    return idle


def mac_ticks_idle(before, after):
    if len(before) != 4 or len(after) != 4 or any(not isinstance(value, int) or not 0 <= value < 2**32
                                               for value in [*before, *after]):
        raise ValueError('Mach CPU load requires four unsigned32 counters')
    delta = [(new - old) % 2**32 for old, new in zip(before, after)]
    if not sum(delta) or any(value >= 2**31 for value in delta):
        raise ValueError('Mach CPU counters did not advance reliably')
    return 100. * delta[2] / sum(delta)


class MachCPUTicks:
    """Verified HOST_CPU_LOAD_INFO ABI; one cached host port per sensor."""
    def __init__(self):
        self.library = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
        self.library.mach_host_self.argtypes = []
        self.library.mach_host_self.restype = ctypes.c_uint
        self.library.host_statistics.argtypes = [ctypes.c_uint, ctypes.c_int,
                                                ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)]
        self.library.host_statistics.restype = ctypes.c_int
        self.port = self.library.mach_host_self()

    def __call__(self):
        counters = (ctypes.c_uint * 4)()
        count = ctypes.c_uint(4)
        code = self.library.host_statistics(self.port, 3, ctypes.cast(counters, ctypes.POINTER(ctypes.c_int)),
                                            ctypes.byref(count))
        if code != 0 or count.value != 4:
            raise OSError(f'Mach host_statistics failed: code={code}, count={count.value}')
        return list(counters)


def linux_idle(before, after):
    rows = [[int(value) for value in text.splitlines()[0].split()[1:9]] for text in (before, after)]
    if any(len(row) != 8 for row in rows):
        raise ValueError('Linux CPU aggregate requires its first eight counters')
    changes = [new - old for old, new in zip(*rows)]
    if any(value < 0 for value in changes) or sum(changes) <= 0:
        raise ValueError('Linux CPU counters did not advance monotonically')
    return 100 * changes[3] / sum(changes)


def free_memory(text):
    rows = {parts[0]: parts[1:] for parts in (line.split() for line in text.splitlines()) if parts}
    return {'available_bytes': int(rows['Mem:'][5]), 'swap_total_bytes': int(rows['Swap:'][0]),
            'swap_used_bytes': int(rows['Swap:'][1])}


def ready(snapshot):
    return snapshot.get('memory_ok') is True and snapshot.get('idle_percent') is not None and snapshot['idle_percent'] >= 80


def unhealthy(snapshot):
    return snapshot.get('memory_ok') is not True or snapshot.get('idle_percent') is None or snapshot['idle_percent'] < 60


def contamination_summary(samples):
    """Version-two external-load decision; never reinterpret legacy receipts."""
    reasons, weighted, duration, maximum = [], 0., 0., None
    if not samples:
        reasons.append('cpu_accounting_unavailable')
    for sample in samples:
        if sample.get('memory_ok') is not True:
            reasons.append('memory_not_ok')
        values = [sample.get(key) for key in ('total_busy_percent', 'job_tree_busy_percent',
                                             'other_busy_percent', 'interval_seconds')]
        if (sample.get('cpu_accounting_valid') is not True or any(not isinstance(value, (int, float))
                or not math.isfinite(value) for value in values) or values[3] <= 0
                or any(not 0 <= value <= 100 for value in values[:3])
                or not math.isclose(values[2], max(0., values[0] - values[1]), abs_tol=1e-6)):
            reasons.append('cpu_accounting_unavailable')
            continue
        weighted += values[2] * values[3]
        duration += values[3]
        maximum = values[2] if maximum is None else max(maximum, values[2])
    mean = weighted / duration if duration else None
    valid = not reasons
    if (mean is not None and mean > 20.) or (maximum is not None and maximum > 40.):
        reasons.append('other_busy')
    return {'valid': valid, 'contended': bool(reasons), 'mean_other_busy_percent': mean,
            'max_other_busy_percent': maximum, 'reasons': sorted(set(reasons))}


def linux_process_stat(text, ticks_per_second):
    pid = int(text.split('(', 1)[0].strip())
    fields = text.rsplit(') ', 1)[1].split()
    values = [int(fields[index]) for index in (11, 12, 13, 14)]
    if any(value < 0 for value in values):
        raise ValueError('Negative process CPU counter')
    return {'pid': pid, 'ppid': int(fields[1]), 'pgid': int(fields[2]), 'session': int(fields[3]),
            'start': fields[19], 'cpu_seconds': (values[0] + values[1]) / ticks_per_second,
            'reaped_cpu_seconds': (values[2] + values[3]) / ticks_per_second, 'state': fields[0]}


def cpu_time_seconds(value):
    days, clock = value.split('-', 1) if '-' in value else ('0', value)
    fields = [float(part) for part in clock.split(':')]
    if len(fields) not in (2, 3) or any(not math.isfinite(part) or part < 0 for part in fields):
        raise ValueError('Malformed cumulative ps CPU time')
    return int(days) * 86400 + sum(part * 60**index for index, part in enumerate(reversed(fields)))


def mac_process_rows(text):
    rows = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        pid, ppid, pgid, cpu, started = line.split(None, 4)
        rows[int(pid)] = {'pid': int(pid), 'ppid': int(ppid), 'pgid': int(pgid), 'session': None,
                          'start': started.strip(), 'cpu_seconds': cpu_time_seconds(cpu),
                          'reaped_cpu_seconds': 0., 'state': 'unknown'}
    return rows


class JobCPUSampler:
    """Read-only CPU accounting for one identity-bound foreground watchdog tree."""
    def __init__(self, root_pid, host=None, *, cpu_count=None, proc_root=Path('/proc')):
        self.root_pid = int(root_pid)
        self.host = host or {'Linux': 'linux', 'Darwin': 'mac'}.get(platform.system())
        self.cpu_count = os.cpu_count() if cpu_count is None else cpu_count
        self.proc_root = Path(proc_root)
        self.root_start = None

    def snapshot(self, *, deadline=HARD_STOP, cancel=None):
        records, errors = {}, []
        began = time.monotonic()
        if self.host == 'mac':
            result = health_command(['ps', '-A', '-o', 'pid=,ppid=,pgid=,time=,lstart='], deadline, cancel)
            try:
                if result['returncode'] or result['interrupted']:
                    raise ValueError('Mac ps process CPU snapshot unavailable')
                records = mac_process_rows(result['stdout'])
            except (ValueError, KeyError) as error:
                errors.append(str(error))
            return {'at': time.monotonic(), 'scan_started': began, 'host': self.host,
                    'records': records, 'valid': not errors, 'errors': errors, 'raw': result}
        if self.host != 'linux':
            raise ValueError('Unsupported process CPU host')
        ticks = os.sysconf('SC_CLK_TCK')
        boot_ticks = int(float((self.proc_root / 'uptime').read_text().split()[0]) * ticks)
        for path in self.proc_root.glob('[0-9]*/stat'):
            try:
                row = linux_process_stat(path.read_text(), ticks)
                records[row['pid']] = row
            except FileNotFoundError:
                continue
            except (OSError, ValueError, IndexError) as error:
                errors.append({'pid': path.parent.name, 'error': str(error)})
        snapshot = {'at': time.monotonic(), 'scan_started': began, 'host': self.host,
                    'boot_ticks': boot_ticks, 'ticks_per_second': ticks,
                    'records': records, 'valid': not errors, 'errors': errors}
        members, ancestry_errors = self.members(snapshot)
        errors.extend(ancestry_errors)
        # A reaping transition during a non-atomic /proc scan could otherwise
        # expose both an old child row and the transferred parent counters.
        for pid, row in members.items():
            try:
                current = linux_process_stat((self.proc_root / str(pid) / 'stat').read_text(), ticks)
                if any(current[key] != row[key] for key in ('start', 'ppid', 'pgid', 'session', 'reaped_cpu_seconds')):
                    errors.append('tree_identity_or_reaping_changed_during_scan')
            except (OSError, ValueError, IndexError):
                errors.append('tree_member_disappeared_during_scan')
        snapshot.update(valid=not errors, errors=errors)
        return snapshot

    def members(self, snapshot):
        records = {int(pid): row for pid, row in snapshot['records'].items()}
        root = records.get(self.root_pid)
        if root is None or root.get('state') == 'Z':
            return {}, ['root_missing']
        members, errors = {}, []
        for pid, row in records.items():
            current, visited = pid, set()
            while current != self.root_pid:
                if current in visited:
                    if row['pgid'] == root['pgid']:
                        errors.append('ancestry_cycle')
                    break
                visited.add(current)
                parent = records.get(current)
                if parent is None:
                    if row['pgid'] == root['pgid']:
                        errors.append('ancestry_unavailable')
                    break
                current = parent['ppid']
                if current <= 0:
                    break
            if current == self.root_pid:
                if row['pgid'] != root['pgid'] or row['session'] != root['session']:
                    errors.append('foreground_group_changed')
                else:
                    members[pid] = row
        return members, errors

    def account(self, before, after):
        interval = after['at'] - before['at']
        first, errors1 = self.members(before)
        last, errors2 = self.members(after)
        errors = [*errors1, *errors2]
        if not before.get('valid') or not after.get('valid'):
            errors.append('process_snapshot_unavailable')
        if interval <= 0 or not self.cpu_count:
            errors.append('invalid_interval_or_capacity')
        root = first.get(self.root_pid)
        if root is not None:
            if self.root_start is None:
                self.root_start = root['start']
            if root['start'] != self.root_start or last.get(self.root_pid, {}).get('start') != self.root_start:
                errors.append('root_identity_changed')
        reused = [pid for pid in first.keys() & last.keys() if first[pid]['start'] != last[pid]['start']]
        if self.host == 'linux' and reused:
            errors.append('pid_reused')
        before_records = {int(pid): row for pid, row in before['records'].items()}
        after_records = {int(pid): row for pid, row in after['records'].items()}
        if self.host == 'linux':
            for pid in first.keys() - last.keys():
                if pid in after_records:
                    errors.append('ancestry_or_identity_changed')
            for pid in last.keys() - first.keys():
                if pid in before_records or int(last[pid]['start']) < before['boot_ticks']:
                    errors.append('unproven_process_birth')
        # Summing own+waited CPU across the LIVE tree replaces vanished child CPU
        # with its parent's cutime/cstime. Subtracting both endpoint totals avoids
        # counting an observed child again when the parent later reaps it.
        total_before = sum(row['cpu_seconds'] + row['reaped_cpu_seconds'] for row in first.values())
        total_after = sum(row['cpu_seconds'] + row['reaped_cpu_seconds'] for row in last.values())
        attributed = set(first) | set(last)
        cpu = total_after - total_before
        if self.host == 'mac':
            attributed = first.keys() & last.keys() - set(reused)
            cpu = sum(last[pid]['cpu_seconds'] - first[pid]['cpu_seconds'] for pid in attributed)
        if cpu < -1e-9:
            errors.append('nonmonotonic_tree_cpu')
        return {'valid': not errors, 'job_cpu_seconds': max(0., cpu) if not errors else None,
                'job_tree_busy_percent': 100 * max(0., cpu) / (interval * self.cpu_count) if not errors else None,
                'interval_seconds': interval, 'interval_start': before['at'], 'interval_end': after['at'],
                'cpu_count': self.cpu_count, 'root_pid': self.root_pid, 'root_start': self.root_start,
                'before_member_pids': sorted(first), 'after_member_pids': sorted(last),
                'attributed_pids': sorted(attributed) if not errors else [],
                'attributed_identities': [{'pid': pid, 'start': (last.get(pid) or first[pid])['start']}
                                          for pid in sorted(attributed)] if not errors else [],
                'unassigned_new_or_departed_pids': sorted((set(first) ^ set(last)) | set(reused)),
                'tree_cpu_seconds_before': total_before, 'tree_cpu_seconds_after': total_after,
                'process_cpu_before': [first[pid] for pid in sorted(first)],
                'process_cpu_after': [last[pid] for pid in sorted(last)],
                'clock_ticks_per_second': before.get('ticks_per_second'),
                'method': ('linux-proc-tree-own-plus-reaped-v2' if self.host == 'linux'
                           else 'mac-ps-stable-descendants-lower-bound-v2'), 'reasons': sorted(set(errors)),
                'snapshot_scan_seconds': [before['at'] - before.get('scan_started', before['at']),
                                          after['at'] - after.get('scan_started', after['at'])]}


def attach_cpu_accounting(health, sampler, before, after):
    accounting = sampler.account(before, after)
    idle = health.get('idle_percent')
    total = 100. - idle if isinstance(idle, (int, float)) and math.isfinite(idle) and 0 <= idle <= 100 else None
    job = accounting['job_tree_busy_percent']
    valid = accounting['valid'] and total is not None and job is not None and 0 <= job <= 100
    health.update(total_busy_percent=total, job_tree_busy_percent=job if valid else None,
                  other_busy_percent=max(0., total - job) if valid else total,
                  interval_seconds=accounting['interval_seconds'], cpu_accounting_valid=valid,
                  cpu_accounting=accounting)
    if not valid:
        accounting['reasons'] = sorted(set([*accounting['reasons'], 'global_or_job_cpu_unavailable']))
    return health


def health_command(argv, deadline, cancel=None):
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    timeout = min(deadline, time.time() + (13 if argv[0] == 'top' else 5))
    interrupted = False
    while True:
        try:
            stdout, stderr = process.communicate(timeout=.1)
            break
        except subprocess.TimeoutExpired:
            if time.time() >= timeout or (cancel is not None and cancel.is_set()):
                interrupted = True
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                break
    return {'argv': argv, 'returncode': process.returncode, 'stdout': stdout, 'stderr': stderr,
            'interrupted': interrupted}


class SystemHealth:
    def __init__(self, host, *, mac_ticks_reader=None, command_reader=None):
        actual = {'Darwin': 'mac', 'Linux': 'linux'}.get(platform.system())
        if host != actual:
            raise ValueError(f'run {host} must execute on that host; this machine is {actual}')
        self.host = host
        self.mac_ticks_reader = mac_ticks_reader
        self.command_reader = health_command if command_reader is None else command_reader

    def sample(self, *, deadline=HARD_STOP, cancel=None, cpu_sampler=None):
        result = {'host': self.host, 'at': time.time(), 'idle_percent': None, 'memory_ok': False,
                  'load_average': list(os.getloadavg()), 'raw': {}}
        if cpu_sampler is not None:
            result.update(total_busy_percent=None, job_tree_busy_percent=None, other_busy_percent=None,
                          interval_seconds=0., cpu_accounting_valid=False,
                          cpu_accounting={'valid': False, 'reasons': ['cpu_window_unavailable']})
        try:
            if self.host == 'mac':
                commands = {'top': ['top', '-l', '2', '-s', '10', '-n', '0'],
                            'memory_pressure': ['memory_pressure', '-Q'],
                            'pressure_level': ['sysctl', 'kern.memorystatus_vm_pressure_level'],
                            'swapusage': ['sysctl', 'vm.swapusage']}
                if cpu_sampler is not None:
                    if self.mac_ticks_reader is None:
                        self.mac_ticks_reader = MachCPUTicks()
                    global_started = time.monotonic()
                    ticks_before = self.mac_ticks_reader()
                    before = cpu_sampler.snapshot(deadline=deadline)
                    delay = min(10., max(0., deadline - time.time()))
                    event = threading.Event() if cancel is None else cancel
                    interrupted = event.wait(delay)
                    after = cpu_sampler.snapshot(deadline=deadline)
                    ticks_after = self.mac_ticks_reader()
                    result['raw'].update(cpu_ticks_before=ticks_before, cpu_ticks_after=ticks_after)
                    result['global_interval_seconds'] = time.monotonic() - global_started
                    result['cpu_source'] = {'api': 'host_statistics(mach_host_self, HOST_CPU_LOAD_INFO=3)',
                                            'counter_bits': 32, 'states': ['user', 'system', 'idle', 'nice'],
                                            'source': 'https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/mach/host_info.h',
                                            'sdk_headers': ['mach/host_info.h', 'mach/machine.h']}
                    result['idle_percent'] = mac_ticks_idle(ticks_before, ticks_after)
                    result['partial_cpu_window'] = interrupted or delay < 10.
                    attach_cpu_accounting(result, cpu_sampler, before, after)
                    del commands['top']
                for name, argv in commands.items():
                    if cancel is not None and cancel.is_set() and cpu_sampler is None:
                        result['cancelled'] = True
                        return result
                    result['raw'][name] = self.command_reader(argv, deadline, None if cpu_sampler is not None else cancel)
                raw = result['raw']
                if cpu_sampler is None:
                    result['idle_percent'] = mac_idle(raw['top']['stdout']) if raw['top']['returncode'] == 0 else None
                level = int(raw['pressure_level']['stdout'].rsplit(':', 1)[-1].strip())
                result['pressure_level'] = level
                result['memory_ok'] = level == 1 and all(raw[name]['returncode'] == 0 and not raw[name]['interrupted'] for name in commands)
            else:
                before = Path('/proc/stat').read_text()
                job_before = cpu_sampler.snapshot(deadline=deadline) if cpu_sampler is not None else None
                delay = min(10., max(0., deadline - time.time()))
                event = threading.Event() if cancel is None else cancel
                interrupted = event.wait(delay)
                if interrupted and cpu_sampler is None:
                    result['cancelled'] = True
                    return result
                job_after = cpu_sampler.snapshot(deadline=deadline) if cpu_sampler is not None else None
                after = Path('/proc/stat').read_text()
                result['raw']['cpu_before'] = before
                result['raw']['cpu_after'] = after
                result['partial_cpu_window'] = interrupted or delay < 10.
                if delay < 10. and cpu_sampler is None:
                    raise ValueError('Deadline shortened the required ten-second CPU sample')
                result['idle_percent'] = linux_idle(before, after)
                if cpu_sampler is not None:
                    attach_cpu_accounting(result, cpu_sampler, job_before, job_after)
                free = health_command(['free', '-b'], deadline, None if cpu_sampler is not None else cancel)
                result['raw']['free'] = free
                memory = free_memory(free['stdout']) if free['returncode'] == 0 else {}
                result.update(memory)
                result['memory_ok'] = free['returncode'] == 0 and memory.get('available_bytes', 0) >= 4 * 1024**3
                for name in ('memory', 'cpu', 'io'):
                    path = Path('/proc/pressure') / name
                    try:
                        result['raw']['psi_' + name] = path.read_text()
                    except OSError as error:
                        result['raw']['psi_' + name] = {'error': str(error)}
        except (OSError, ValueError, KeyError, IndexError) as error:
            result['error'] = str(error)
        result['finished_at'] = time.time()
        return result


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def _not_executed(receipt):
    # Missing legacy evidence is ambiguous and must still spend the budget.
    return receipt.get('rejected_before_exec') is True or receipt.get('execution_started') is False


def _execution_count(job):
    return sum(not _not_executed(read_json(path, {})) for path in job['attempts'])


@contextmanager
def file_lock(path, nonblocking=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
        try:
            yield stream
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class Queue:
    def __init__(self, root=DEFAULT_STORAGE):
        self.root = Path(root).resolve()

    def host_dir(self, host):
        if host not in HOSTS:
            raise ValueError('Host must be mac or linux')
        return self.root / host

    def jobs(self, host):
        return sorted((read_json(path) for path in (self.host_dir(host) / 'jobs').glob('*/job.json')),
                      key=lambda job: (job['priority'], job['order'], job['id']))

    def enqueue(self, host, name, argv, *, cwd=None, lane='root', priority=None, receipts=()):
        directory = self.host_dir(host)
        cwd = Path.cwd() if cwd is None else Path(cwd)
        cwd = cwd.resolve()
        if not cwd.is_dir() or not argv or not all(isinstance(value, str) and '\0' not in value for value in argv):
            raise ValueError('A real cwd and nonempty literal argv are required')
        priority = (1 if lane == 'root' else 2) if priority is None else priority
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 1:
            raise ValueError('Priority must be a positive integer')
        with file_lock(directory / 'queue.lock'):
            if read_json(directory / 'sealed.json', {}).get('sealed'):
                raise ValueError('Queue is sealed; open it before adding producer submissions')
            jobs = self.jobs(host)
            identifier = uuid.uuid4().hex
            job = {'id': identifier, 'host': host, 'name': name, 'cwd': str(cwd), 'argv': list(argv),
                   'lane': lane, 'priority': priority, 'receipts': list(receipts),
                   'created_at': time.time(), 'order': max((row['order'] for row in jobs), default=0) + 1,
                   'state': 'pending', 'attempts': [], 'preexec_rejections': []}
            atomic_json(directory / 'jobs' / identifier / 'job.json', job)
        return job

    def seal(self, host, sealed=True):
        directory = self.host_dir(host)
        with file_lock(directory / 'queue.lock'):
            atomic_json(directory / 'sealed.json', {'sealed': sealed, 'at': time.time()})

    def status(self, host=None):
        result = {}
        for name in HOSTS if host is None else (host,):
            directory = self.host_dir(name)
            with file_lock(directory / 'queue.lock'):
                runner = read_json(directory / 'runner.json')
                if runner is not None:
                    runner['identity_matches'] = process_identity(runner['pid']) == runner.get('identity')
                result[name] = {'sealed': read_json(directory / 'sealed.json', {}).get('sealed', False),
                                'runner': runner, 'jobs': self.jobs(name)}
        return result

    def stop(self, host):
        atomic_json(self.host_dir(host) / 'stop.json', {'requested_at': time.time()})

    def recover(self, host):
        """Retain crash evidence; never signal a PID discovered from stale state."""
        directory = self.host_dir(host)
        recoverable, live = [], []
        with file_lock(directory / 'queue.lock'):
            for job in self.jobs(host):
                attempts = sorted((directory / 'jobs' / job['id'] / 'attempts').glob('*/attempt.json'))
                known = set(job['attempts']) | set(job.get('preexec_rejections', []))
                extra = [str(path) for path in attempts if str(path) not in known]
                if extra:
                    job['attempts'].extend(extra)
                    job['state'] = 'running'
                    atomic_json(directory / 'jobs' / job['id'] / 'job.json', job)
                if job['state'] == 'exhausted-contended' and _execution_count(job) < 3:
                    job['state'] = 'pending'
                    atomic_json(directory / 'jobs' / job['id'] / 'job.json', job)
                if job['state'] != 'running':
                    continue
                attempt_dir = Path(job['attempts'][-1]).parent
                old = read_json(attempt_dir / 'attempt.json', {})
                if old.get('phase') == 'closed':
                    recoverable.append((job, attempt_dir, old))
                    continue
                child = read_json(attempt_dir / 'child.json')
                if child is not None and process_identity(child['pid']) == child:
                    launch = read_json(attempt_dir / 'launch.json', {})
                    if launch.get('sampling_ack') and (attempt_dir / 'command-exit.json').exists():
                        atomic_json(attempt_dir / 'sampling-complete.json', {'abandoned_after_runner_crash': True, 'at': time.time()})
                    live.append({'job': job['id'], 'attempt': old.get('attempt', int(attempt_dir.name)), 'child_identity': child})
                    continue
                receipt = {'phase': 'closed', 'started_at': old.get('started_at'), 'finished_at': time.time(),
                           'attempt': old.get('attempt', int(attempt_dir.name)),
                           'execution_started': (old.get('execution_started', True) or child is not None
                                                 or (attempt_dir / 'command-exit.json').exists()),
                           'rejected_before_exec': old.get('rejected_before_exec', False),
                           'execution_attempt': old.get('execution_attempt'),
                           'returncode': read_json(attempt_dir / 'command-exit.json', {}).get('returncode'),
                           'contended': True, 'recovered_after_runner_crash': True,
                           'start_health': read_json(attempt_dir / 'start-health.json', {'unavailable': 'runner crashed before recording START'}),
                           'end_health': {'unavailable': 'runner crashed; no END sample was recorded'},
                           'periodic_health': read_json(attempt_dir / 'periodic-health.json', []),
                           'stdout': str(attempt_dir / 'stdout.log'), 'stderr': str(attempt_dir / 'stderr.log'),
                           'benchmark_verdict': 'unassessed', 'receipts': []}
                if old.get('contamination_policy') == 'other-busy-v2':
                    receipt.update(contamination_policy='other-busy-v2',
                                   contamination=contamination_summary(receipt['periodic_health']))
                recoverable.append((job, attempt_dir, receipt))
        for job, attempt_dir, receipt in recoverable:
            self.finish(job, attempt_dir, receipt)
        return live

    def begin(self, host):
        directory = self.host_dir(host)
        with file_lock(directory / 'queue.lock'):
            pending = [job for job in self.jobs(host) if job['state'] == 'pending']
            if not pending:
                return None
            job = pending[0]
            if _execution_count(job) >= 3:
                job['state'] = 'exhausted-contended'
                atomic_json(directory / 'jobs' / job['id'] / 'job.json', job)
                return None
            trials = directory / 'jobs' / job['id'] / 'attempts'
            ordinals = [int(path.name) for path in trials.iterdir() if path.name.isdecimal()] if trials.exists() else []
            number = max(ordinals, default=0) + 1
            attempt_dir = trials / f'{number:03d}'
            attempt_dir.mkdir(parents=True, exist_ok=False)
            receipt = attempt_dir / 'attempt.json'
            atomic_json(receipt, {'phase': 'starting', 'started_at': time.time(), 'attempt': number,
                                  'execution_started': False,
                                  'contamination_policy': 'other-busy-v2'})
            job['state'] = 'running'
            job['attempts'].append(str(receipt))
            atomic_json(directory / 'jobs' / job['id'] / 'job.json', job)
            return job, attempt_dir

    def finish(self, job, attempt_dir, receipt):
        directory = self.host_dir(job['host'])
        with file_lock(directory / 'queue.lock'):
            job = read_json(directory / 'jobs' / job['id'] / 'job.json')
            path = attempt_dir / 'attempt.json'
            if read_json(path) != receipt:
                atomic_json(path, receipt)
            if _not_executed(receipt):
                job['attempts'].remove(str(path))
                job.setdefault('preexec_rejections', []).append(str(path))
            if receipt['contended'] or _not_executed(receipt):
                job['state'] = 'pending' if _execution_count(job) < 3 else 'exhausted-contended'
                job['order'] = max(row['order'] for row in self.jobs(job['host'])) + 1
            else:
                job['state'] = 'completed' if receipt['returncode'] == 0 else 'failed'
            atomic_json(directory / 'jobs' / job['id'] / 'job.json', job)


class PerlLease:
    """BSD flock acquired by Perl on a shared open file description.

    The Python owner retains the same descriptor after Perl exits, and passes
    it to the foreground job wrapper. This interoperates with scripts/host-lock.
    """
    def __init__(self, path=PERF_LOCK):
        self.path = Path(path)
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        result = subprocess.run(['perl', '-MFcntl=:flock', '-e',
                                 'open my $f,"+<&=".$ARGV[0] or die $!; exit(flock($f,LOCK_EX|LOCK_NB)?0:75)',
                                 str(self.fd)], pass_fds=(self.fd,), capture_output=True, text=True)
        if result.returncode:
            os.close(self.fd)
            self.fd = None
            if result.returncode == 75:
                raise BlockingIOError('The canonical performance lease is busy')
            raise RuntimeError('Perl flock failed: ' + result.stderr)
        return self

    def __exit__(self, *error):
        os.close(self.fd)
        self.fd = None


def process_identity(pid):
    try:
        if platform.system() == 'Linux':
            values = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()
            if values[0] == 'Z':
                return None
            command = Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace').strip()
            return {'pid': pid, 'started': values[19], 'command': command}
        started = subprocess.check_output(['ps', '-p', str(pid), '-o', 'lstart='], text=True, timeout=2).strip()
        command = subprocess.check_output(['ps', '-p', str(pid), '-o', 'command='], text=True, timeout=2).strip()
        return {'pid': pid, 'started': started, 'command': command} if started else None
    except (OSError, IndexError, subprocess.SubprocessError):
        return None


def stop_requested(path, started):
    return read_json(path, {}).get('requested_at', 0) >= started


def execute_child(launch_path):
    """Foreground watchdog; survives a runner crash and owns only its session."""
    if os.getpgrp() != os.getpid():
        raise RuntimeError('The internal job watchdog requires its own process group')
    launch = read_json(launch_path)
    lease_fd = int(os.environ['IRL_SHIELD_PERF_QUEUE_LEASE_FD'])
    expected = Path(launch['lease_path']).stat()
    actual = os.fstat(lease_fd)
    if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
        raise RuntimeError('Inherited queue lease descriptor does not identify its performance lock')
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    process = subprocess.Popen(launch['argv'], cwd=launch['cwd'], close_fds=False)
    atomic_json(Path(launch_path).with_name('child.json'), process_identity(os.getpid()))
    while process.poll() is None:
        hard = time.time() >= launch['hard_stop'] - .1
        if hard:
            os.killpg(os.getpgrp(), signal.SIGKILL)
        if stop.is_set() or stop_requested(launch['stop_path'], launch['run_started']):
            os.killpg(os.getpgrp(), signal.SIGTERM)
            try:
                process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgrp(), signal.SIGKILL)
        time.sleep(.05)
    atomic_json(Path(launch_path).with_name('command-exit.json'), {'returncode': process.returncode, 'at': time.time()})
    while launch.get('sampling_ack') and not Path(launch_path).with_name('sampling-complete.json').exists():
        if time.time() >= launch['hard_stop'] - .1:
            os.killpg(os.getpgrp(), signal.SIGKILL)
        if stop.is_set() or stop_requested(launch['stop_path'], launch['run_started']):
            break
        time.sleep(.01)
    return process.returncode if process.returncode >= 0 else 128 - process.returncode


class Runner:
    def __init__(self, queue, host, *, sensor=None, perf_lock=PERF_LOCK, readiness_period=120.,
                 sample_period=10., force_at=FORCE_AT, hard_stop=HARD_STOP):
        self.queue, self.host = queue, host
        self.sensor = SystemHealth(host) if sensor is None else sensor
        self.perf_lock = perf_lock
        self.readiness_period, self.sample_period = readiness_period, sample_period
        self.force_at, self.hard_stop = force_at, hard_stop
        self.directory = queue.host_dir(host)
        self.control = threading.Event()
        self.finished = threading.Event()
        self.reason = None
        self.started = time.time()
        self.identity = process_identity(os.getpid())
        self.stop_path = self.directory / 'stop.json'

    def state(self, value, **details):
        atomic_json(self.directory / 'runner.json', {'host': self.host, 'pid': os.getpid(),
                    'identity': self.identity, 'started_at': self.started,
                    'state': value, 'updated_at': time.time(),
                    'stop_command': [str(ROOT / 'scripts/perf-queue'), '--queue-dir', str(self.queue.root), 'stop', self.host],
                    **details})

    def watch_control(self):
        while not self.finished.wait(.05):
            if time.time() >= self.hard_stop - .1:
                self.reason = 'hard-stop'
                self.control.set()
            elif stop_requested(self.stop_path, self.started):
                self.reason = 'stop-requested'
                self.control.set()

    def run(self):
        # Alternate queue directories must not create a second runner on this host.
        host_runner = Path(self.perf_lock).with_name('perf-runner.lock')
        with file_lock(host_runner, nonblocking=True), file_lock(self.directory / 'runner.lock', nonblocking=True):
            watcher = threading.Thread(target=self.watch_control, daemon=True)
            watcher.start()
            try:
                if time.time() >= self.hard_stop - .1:
                    self.reason = 'hard-stop'
                    self.control.set()
                while not self.control.is_set():
                    live = self.queue.recover(self.host)
                    if live:
                        self.state('waiting-for-orphan-attempt', attempts=live)
                        self.control.wait(self.readiness_period)
                        continue
                    jobs = self.queue.jobs(self.host)
                    pending = [job for job in jobs if job['state'] == 'pending']
                    if not pending:
                        if read_json(self.directory / 'sealed.json', {}).get('sealed', False):
                            self.state('drained')
                            return 'drained'
                        self.state('waiting-for-producers')
                        self.control.wait(self.readiness_period)
                        continue
                    self.state('checking-readiness')
                    check_started = time.monotonic()
                    health = self.sensor.sample(deadline=self.hard_stop, cancel=self.control)
                    atomic_json(self.directory / 'readiness.json', health)
                    atomic_json(self.directory / 'readiness' / f'{time.time_ns()}.json', health)
                    forced = time.time() >= self.force_at
                    if not ready(health) and not forced:
                        self.state('waiting-for-quiet', health=health)
                        self.control.wait(min(max(0., self.readiness_period - (time.monotonic() - check_started)),
                                              max(0., self.force_at - time.time())))
                        continue
                    if self.control.is_set():
                        break
                    if time.time() >= self.hard_stop - .1:
                        self.reason = 'hard-stop'
                        self.control.set()
                        break
                    try:
                        with PerlLease(self.perf_lock) as lease:
                            selected = self.queue.begin(self.host)
                            if selected is not None:
                                self.attempt(*selected, lease, forced)
                    except BlockingIOError:
                        self.state('waiting-for-performance-lease')
                        self.control.wait(max(0., self.readiness_period - (time.monotonic() - check_started)))
                self.state(self.reason or 'stopped')
                return self.reason or 'stopped'
            finally:
                self.finished.set()
                watcher.join(timeout=1)

    def attempt(self, job, directory, lease, forced):
        started = time.time()
        start = self.sensor.sample(deadline=self.hard_stop, cancel=self.control)
        atomic_json(directory / 'start-health.json', start)
        forced = forced or time.time() >= self.force_at
        samples = []
        cancel = threading.Event()
        sampling_closed = threading.Event()
        sample_lock = threading.Lock()
        number = int(directory.name)
        execution_attempt = _execution_count(job) + 1
        job_dir = self.queue.host_dir(self.host) / 'jobs' / job['id']
        expand = lambda value: value.replace('{attempt}', str(number)).replace('{job_dir}', str(job_dir))
        argv = [expand(value) for value in job['argv']]
        stdout, stderr = directory / 'stdout.log', directory / 'stderr.log'
        rejected = not forced and not ready(start)
        process = None
        identity = None
        monitor = None
        returncode = None
        error = None
        queue_environment = {'IRL_SHIELD_PERF_QUEUE_FORCED': '1' if forced else '0',
                             'IRL_SHIELD_PERF_QUEUE_ATTEMPT': str(number),
                             'IRL_SHIELD_PERF_QUEUE_RECEIPT': str(directory / 'attempt.json'),
                             'IRL_SHIELD_PERF_QUEUE_LEASE_FD': str(lease.fd)}
        prepared = {'phase': 'prepared', 'started_at': started,
                    'job': job['id'], 'host': self.host, 'attempt': number, 'forced': forced,
                    'execution_started': False, 'execution_attempt': None,
                    'contamination_policy': 'other-busy-v2',
                    'queue_environment': queue_environment, 'lease_path': str(self.perf_lock),
                    'lease_identity': {'device': os.fstat(lease.fd).st_dev, 'inode': os.fstat(lease.fd).st_ino}}
        atomic_json(directory / 'attempt.json', prepared)

        def observe(cpu_sampler):
            while True:
                began = time.monotonic()
                try:
                    sample = self.sensor.sample(deadline=self.hard_stop, cancel=cancel, cpu_sampler=cpu_sampler)
                except Exception as cause:
                    sample = {'idle_percent': None, 'memory_ok': False, 'cpu_accounting_valid': False,
                              'error': f'{type(cause).__name__}: {cause}'}
                with sample_lock:
                    if sampling_closed.is_set():
                        return
                    if not sample.get('cancelled'):
                        samples.append(sample)
                        atomic_json(directory / 'periodic-health.json', samples)
                if cancel.is_set():
                    return
                cancel.wait(max(0., self.sample_period - (time.monotonic() - began)))

        try:
            if not rejected and not self.control.is_set():
                launch = {'argv': argv, 'cwd': job['cwd'], 'hard_stop': self.hard_stop,
                          'stop_path': str(self.stop_path), 'run_started': self.started,
                          'sampling_ack': True,
                          'lease_path': str(self.perf_lock), 'queue_environment': queue_environment}
                atomic_json(directory / 'launch.json', launch)
                with stdout.open('w') as out, stderr.open('w') as err:
                    # Commit launch before spawning: a crash in the spawn window
                    # is ambiguous, so recovery must charge it conservatively.
                    atomic_json(directory / 'attempt.json', prepared | {'execution_started': True,
                                'execution_attempt': execution_attempt})
                    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_exec', str(directory / 'launch.json')],
                                               cwd=job['cwd'], stdout=out, stderr=err,
                                               start_new_session=True, pass_fds=(lease.fd,),
                                               env=os.environ | queue_environment)
                    identity = process_identity(process.pid)
                    self.state('running', job=job['id'], attempt=number, child_identity=identity)
                    cpu_sampler = JobCPUSampler(process.pid, host=self.host)
                    monitor = threading.Thread(target=observe, args=(cpu_sampler,), daemon=True)
                    monitor.start()
                    while process.poll() is None:
                        if (directory / 'command-exit.json').exists():
                            cancel.set()
                            monitor.join(timeout=3)
                            with sample_lock:
                                if monitor.is_alive():
                                    samples.append({'memory_ok': False, 'cpu_accounting_valid': False,
                                                    'error': 'Final CPU sample did not close before ACK'})
                                    atomic_json(directory / 'periodic-health.json', samples)
                                sampling_closed.set()
                            atomic_json(directory / 'sampling-complete.json', {'at': time.time()})
                            process.wait(timeout=1)
                            break
                        if self.control.wait(.05):
                            if process_identity(process.pid) == identity:
                                os.killpg(process.pid, signal.SIGKILL if self.reason == 'hard-stop' else signal.SIGTERM)
                            try:
                                process.wait(timeout=.6)
                            except subprocess.TimeoutExpired:
                                if process_identity(process.pid) == identity:
                                    os.killpg(process.pid, signal.SIGKILL)
                                process.wait()
                    returncode = read_json(directory / 'command-exit.json', {}).get('returncode', process.returncode)
                    if time.time() >= self.hard_stop - .15:
                        self.reason = 'hard-stop'
                        self.control.set()
                    elif stop_requested(self.stop_path, self.started):
                        self.reason = 'stop-requested'
                        self.control.set()
        except BaseException as cause:
            error = f'{type(cause).__name__}: {cause}'
            self.reason = 'interrupted'
            self.control.set()
            self.queue.stop(self.host)
            if process is not None and process.poll() is None:
                if process_identity(process.pid) == identity:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        finally:
            cancel.set()
            if monitor is not None:
                monitor.join(timeout=3)
            with sample_lock:
                sampling_closed.set()
        end = (self.sensor.sample(deadline=self.hard_stop, cancel=self.control) if not self.control.is_set()
               else {'idle_percent': None, 'memory_ok': False, 'unavailable': self.reason})
        atomic_json(directory / 'end-health.json', end)
        artifacts = []
        for template in job['receipts']:
            path = Path(expand(template))
            path = path if path.is_absolute() else Path(job['cwd']) / path
            row = {'path': str(path), 'exists': path.exists()}
            if path.is_file():
                row.update(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            artifacts.append(row)
        contamination = contamination_summary(samples)
        outside_health_bad = (start.get('memory_ok') is not True or end.get('memory_ok') is not True
                              or end.get('idle_percent') is None)
        receipt = {'phase': 'closed', 'started_at': started, 'finished_at': time.time(), 'attempt': number,
                   'execution_started': process is not None,
                   'execution_attempt': execution_attempt if process is not None else None,
                   'argv': argv, 'cwd': job['cwd'], 'stdout': str(stdout), 'stderr': str(stderr),
                   'start_health': start, 'end_health': end, 'periodic_health': samples,
                   'forced': forced, 'rejected_before_exec': rejected, 'returncode': returncode,
                   'contamination_policy': 'other-busy-v2', 'contamination': contamination,
                   'contended': forced or rejected or contamination['contended'] or outside_health_bad or self.reason is not None,
                   'error': error, 'stop_reason': self.reason, 'child_identity': identity,
                   'queue_environment': queue_environment,
                   'wrapper_returncode': process.returncode if process is not None else None,
                   'receipts': artifacts, 'benchmark_verdict': 'unassessed'}
        self.queue.finish(job, directory, receipt)


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    command = []
    if '--' in raw:
        index = raw.index('--')
        raw, command = raw[:index], raw[index + 1:]
    if raw[:1] == ['_exec']:
        raise SystemExit(execute_child(Path(raw[1])))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue-dir', type=Path, default=DEFAULT_STORAGE)
    actions = parser.add_subparsers(dest='action', required=True)
    enqueue = actions.add_parser('enqueue')
    enqueue.add_argument('host', choices=HOSTS)
    enqueue.add_argument('job')
    enqueue.add_argument('--lane', default='root')
    enqueue.add_argument('--priority', type=int)
    enqueue.add_argument('--cwd', type=Path)
    enqueue.add_argument('--receipt', action='append', default=[])
    status = actions.add_parser('status')
    status.add_argument('host', choices=HOSTS, nargs='?')
    for action in ('seal', 'open', 'run', 'stop'):
        actions.add_parser(action).add_argument('host', choices=HOSTS)
    args = parser.parse_args(raw)
    queue = Queue(args.queue_dir)
    if args.action == 'enqueue':
        if not command:
            parser.error('enqueue requires -- followed by literal command arguments')
        result = queue.enqueue(args.host, args.job, command, cwd=args.cwd, lane=args.lane,
                               priority=args.priority, receipts=args.receipt)
    elif args.action in ('seal', 'open'):
        queue.seal(args.host, args.action == 'seal')
        result = queue.status(args.host)
    elif args.action == 'run':
        reason = Runner(queue, args.host).run()
        result = queue.status(args.host)
        if reason == 'hard-stop':
            print(json.dumps(result, indent=2), flush=True)
            raise SystemExit(2)
    elif args.action == 'stop':
        queue.stop(args.host)
        result = queue.status(args.host)
    else:
        result = queue.status(args.host)
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == '__main__':
    main()
