"""Real pass/violation/revert/pass proof for external CPU attribution.

Uses stdlib processes and existing host sensors only; no models, data or package
install. Every burner is owned, nice19 and bounded. The3-worker burner is a
sibling of the4-worker job, so it must never enter that job's CPU tree.
"""
import argparse
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from bench.perf_queue import (HARD_STOP, JobCPUSampler, PerlLease, SystemHealth,
                             atomic_json, contamination_summary, process_identity, ready)


def cpu_burn(stop_path, deadline, parent):
    value = 1
    while time.time() < deadline and os.getppid() == parent and not Path(stop_path).exists():
        for _ in range(20000):
            value = (value * 1664525 + 1013904223) & 0xffffffff


def burn_group(workers, folder, deadline):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    stop = folder / 'stop'
    parent = os.getppid()
    def interrupted(*_):
        stop.touch()
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    os.nice(max(0, 19 - os.getpriority(os.PRIO_PROCESS, 0)))
    # This is a fresh stdlib-only process without native framework threads.
    # fork avoids a persistent multiprocessing resource-tracker process.
    context = multiprocessing.get_context('fork')
    children = [context.Process(target=cpu_burn, args=(str(stop), deadline, os.getpid()))
                for _ in range(workers)]
    try:
        for child in children:
            child.start()
        atomic_json(folder / 'ready.json', {'root': process_identity(os.getpid()),
                    'children': [process_identity(child.pid) for child in children],
                    'workers': workers, 'deadline': deadline})
        while time.time() < deadline and os.getppid() == parent and not stop.exists():
            time.sleep(.05)
    finally:
        stop.touch()
        for child in children:
            child.join(timeout=2)
            if child.is_alive():
                child.terminate()
                child.join(timeout=2)
            if child.is_alive():
                child.kill()
                child.join(timeout=2)
        if any(child.is_alive() for child in children):
            raise RuntimeError('An owned synthetic CPU worker survived cleanup')


def start_group(workers, folder, deadline):
    command = [sys.executable, '-u', '-m', 'bench.perf_policy_proof', '_burn',
               '--workers', str(workers), '--out', str(folder), '--deadline', str(deadline)]
    log = (folder.parent / (folder.name + '.log')).open('w')
    try:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
    finally:
        log.close()
    expires = time.monotonic() + 10
    while not (folder / 'ready.json').exists():
        if child.poll() is not None or time.monotonic() >= expires:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=3)
            raise RuntimeError('Owned burner did not produce its ready receipt')
        time.sleep(.05)
    return child, json.loads((folder / 'ready.json').read_text())


def stop_group(child, folder, identity):
    (folder / 'stop').touch()
    if child.poll() is None:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                # The unreaped Popen session leader remains our own process.
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=3)
    known = [identity['root'], *identity['children']]
    alive = [row for row in known if row is not None and process_identity(row['pid']) == row]
    if alive:
        raise RuntimeError('Owned burner identities still alive after cleanup: ' + str([row['pid'] for row in alive]))
    return {'root_pid': child.pid, 'returncode': child.returncode, 'all_known_identities_exited': True}


def exercise(host, directory, samples_per_phase):
    sensor = SystemHealth(host)
    deadline = min(HARD_STOP, time.time() + 210)
    owned = []
    rows = []
    cleanup = []
    proof = {'host': host, 'scope': 'Real synthetic4-core job, separate3-core sibling, then removal; all owned burners at nice19. No video/privacy inference.',
             'at': time.time(), 'phases': rows, 'cleanup': cleanup, 'pass': False}
    try:
        job, identity = start_group(4, directory / 'job-four', deadline)
        owned.append((job, directory / 'job-four', identity))
        sampler = JobCPUSampler(job.pid, host=host)
        foreign = None
        foreign_pids = set()
        for phase in ('clean-before', 'external-burner', 'clean-after'):
            if phase == 'external-burner':
                foreign, other_identity = start_group(3, directory / 'other-three', deadline)
                owned.append((foreign, directory / 'other-three', other_identity))
                foreign_pids = {row['pid'] for row in [other_identity['root'], *other_identity['children']] if row is not None}
            elif phase == 'clean-after':
                cleanup.append(stop_group(*owned.pop()))
                foreign = None
            time.sleep(.5)
            samples = []
            for _ in range(samples_per_phase):
                if job.poll() is not None:
                    raise RuntimeError('The4-worker job exited before proof completed')
                sample = sensor.sample(cpu_sampler=sampler, deadline=deadline)
                samples.append(sample)
                atomic_json(directory / (phase + '-samples.json'), samples)
                attributed = set(sample.get('cpu_accounting', {}).get('attributed_pids', []))
                if sample.get('cpu_accounting_valid') and attributed & foreign_pids:
                    raise RuntimeError('Foreign sibling was incorrectly attributed to the job')
            summary = contamination_summary(samples)
            expected_contended = phase == 'external-burner'
            passed = (summary['valid'] and summary['contended'] == expected_contended
                      and (not expected_contended or 'other_busy' in summary['reasons']))
            four_pids = {row['pid'] for row in identity['children'] if row is not None}
            all_workers_attributed = all(
                four_pids <= set(sample.get('cpu_accounting', {}).get('attributed_pids', []))
                for sample in samples)
            heavy_job_observed = any(sample.get('job_tree_busy_percent', 0) >= 40
                                     and sample.get('total_busy_percent', 0) > 40 for sample in samples)
            passed = passed and all_workers_attributed and (expected_contended or heavy_job_observed)
            row = {'phase': phase, 'expected_contended': expected_contended, 'summary': summary,
                   'pass': passed, 'job_identity': identity, 'foreign_pids': sorted(foreign_pids),
                   'foreign_never_attributed': True, 'all_four_workers_attributed': all_workers_attributed,
                   'heavy_job_observed': heavy_job_observed, 'samples': samples}
            rows.append(row)
            atomic_json(directory / 'proof.json', proof)
            print(json.dumps({key: row[key] for key in ('phase', 'pass', 'summary', 'foreign_never_attributed')}), flush=True)
        proof['pass'] = len(rows) == 3 and all(row['pass'] for row in rows)
    except BaseException as error:
        proof['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        for item in reversed(owned):
            cleanup.append(stop_group(*item))
        proof['finished_at'] = time.time()
        atomic_json(directory / 'proof.json', proof)
    return proof


def main():
    if sys.argv[1:2] == ['_burn']:
        parser = argparse.ArgumentParser()
        parser.add_argument('_burn'); parser.add_argument('--workers', type=int, required=True)
        parser.add_argument('--out', type=Path, required=True); parser.add_argument('--deadline', type=float, required=True)
        args = parser.parse_args()
        if not 1 <= args.workers <= 4:
            parser.error('Only1to4 owned workers are allowed')
        burn_group(args.workers, args.out, args.deadline)
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=('linux', 'mac'), required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--samples-per-phase', type=int, default=3)
    parser.add_argument('--wait-until', type=float, default=time.time() + 1200)
    parser.add_argument('--minimum-ready-idle', type=float, default=85.)
    parser.add_argument('--readiness-period', type=float, default=120.)
    parser.add_argument('--already-locked', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.samples_per_phase <= 3 or not 80 <= args.minimum_ready_idle <= 95:
        parser.error('Proof supports1to3samples/phase and80to95% idle; production readiness remains80%')
    args.out.mkdir(parents=True, exist_ok=False)
    def interrupted(number, frame):
        raise SystemExit(128 + number)
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, interrupted)
    sensor = SystemHealth(args.host)
    while time.time() < args.wait_until:
        health = sensor.sample(deadline=min(args.wait_until, HARD_STOP))
        atomic_json(args.out / 'readiness.json', health)
        if ready(health) and health['idle_percent'] >= args.minimum_ready_idle:
            break
        print(json.dumps({'phase': 'waiting-for-proof-readiness', 'idle_percent': health['idle_percent'],
                          'memory_ok': health['memory_ok']}), flush=True)
        remaining = min(max(0, args.readiness_period - 10), max(0, args.wait_until - time.time()))
        while remaining > 0:
            delay = min(5, remaining); time.sleep(delay); remaining -= delay
    else:
        atomic_json(args.out / 'proof.json', {'pass': False, 'blocked': 'Host did not reach required quiet readiness; no burner started'})
        raise SystemExit(3)
    if args.already_locked:
        descriptor = int(os.environ['IRL_SHIELD_PERF_QUEUE_LEASE_FD'])
        actual, expected = os.fstat(descriptor), Path('/tmp/agents/irl-shield/perf.lock').stat()
        if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise RuntimeError('Queue lease descriptor mismatch')
        result = exercise(args.host, args.out, args.samples_per_phase)
    else:
        with PerlLease():
            result = exercise(args.host, args.out, args.samples_per_phase)
    raise SystemExit(0 if result['pass'] else 2)


if __name__ == '__main__':
    main()
