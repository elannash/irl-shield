"""Join immutable benchmark artifacts with their queue contamination receipts.

A normal endpoint memory snapshot alone cannot establish an accepted timed run.
This report reads evidence without modifying it. No dependency/model is added.
"""
import argparse
import hashlib
import json
from pathlib import Path

from bench.clocked_bench import clock_guards
from bench.clocked_pipeline import performance_trust
from bench.perf_queue import DEFAULT_STORAGE, Queue, unhealthy


def queue_attempt_clean(attempt):
    samples = [attempt.get('start_health', {}), attempt.get('end_health', {}),
               *attempt.get('periodic_health', [])]
    base = (attempt.get('phase') == 'closed' and not attempt.get('contended', True)
            and not attempt.get('forced', False) and not attempt.get('rejected_before_exec', False))
    policy = attempt.get('contamination_policy')
    if policy == 'other-busy-v2':
        from bench.perf_queue import contamination_summary
        measured = contamination_summary(attempt.get('periodic_health', []))
        return (base and all(sample.get('memory_ok') is True for sample in samples)
                and measured['valid'] and not measured['contended'])
    if policy not in (None, 'total-idle-v1'):
        return False
    return base and all(not unhealthy(sample) for sample in samples)


def report(queue_dir=DEFAULT_STORAGE, host=None):
    status = Queue(queue_dir).status(host)
    rows = []
    for machine, state in status.items():
        for job in state['jobs']:
            for receipt_path in job['attempts']:
                attempt = json.loads(Path(receipt_path).read_text())
                if attempt.get('phase') != 'closed':
                    continue
                samples = [attempt.get('start_health', {}), attempt.get('end_health', {}),
                           *attempt.get('periodic_health', [])]
                queue_clean = queue_attempt_clean(attempt)
                for artifact in attempt.get('receipts', []):
                    path = Path(artifact['path'])
                    if not path.name.endswith('.performance.json'):
                        continue
                    row = {'host': machine, 'job': job['name'], 'lane': job['lane'],
                           'job_state': job['state'], 'attempt': attempt.get('attempt'),
                           'queue_receipt': receipt_path, 'performance_receipt': str(path),
                           'returncode': attempt.get('returncode'), 'queue_clean': queue_clean,
                           'measurement_trusted': False, 'rejection_reasons': [],
                           'start_idle_percent': samples[0].get('idle_percent'),
                           'end_idle_percent': samples[1].get('idle_percent'),
                           'minimum_sampled_idle_percent': min((sample['idle_percent'] for sample in samples
                                                                if sample.get('idle_percent') is not None), default=None)}
                    row['contamination_policy'] = attempt.get('contamination_policy', 'total-idle-v1')
                    if row['contamination_policy'] == 'other-busy-v2':
                        from bench.perf_queue import contamination_summary
                        external = contamination_summary(attempt.get('periodic_health', []))
                        row['mean_other_busy_percent'] = external['mean_other_busy_percent']
                        row['max_other_busy_percent'] = external['max_other_busy_percent']
                        row['rejection_reasons'].extend('queue-' + reason for reason in external['reasons'])
                    if not queue_clean:
                        row['rejection_reasons'].append('queue-contended')
                    try:
                        data = path.read_bytes()
                        if (not artifact.get('exists') or len(data) != artifact['bytes']
                                or hashlib.sha256(data).hexdigest() != artifact['sha256']):
                            raise ValueError('artifact hash/size differs from queue receipt')
                        performance = json.loads(data)
                        endpoint = performance_trust(performance)
                        row['rejection_reasons'].extend(endpoint['reasons'])
                        trusted = queue_clean and endpoint['valid'] and performance.get('performance_valid', False)
                        guards = clock_guards(performance, required_resolution=tuple(performance['resolution']))
                        guards['throughput'] = guards['throughput'] and trusted
                        guards['latency'] = guards['latency'] and trusted
                        row.update(measurement_trusted=trusted, clock_guards=guards,
                                   candidate=performance.get('candidate'), encoder=performance.get('encoder'),
                                   options=performance.get('options'), resolution=performance['resolution'],
                                   steady_fps=performance['output_wall_rate_fps'],
                                   steady_p95_seconds=performance['realtime_added_latency_seconds']['p95'],
                                   presentation_delay_seconds=performance.get('presentation_delay_seconds'),
                                   protected_fraction=performance['protected_fraction'],
                                   startup=performance.get('startup'), engine=performance.get('engine'),
                                   cpu_percent_one_core_100=performance.get('cpu_percent_one_core_100'),
                                   peak_tree_rss_mb=performance.get('peak_tree_rss_mb'),
                                   perf_health=performance.get('perf_health'),
                                   pipeline_sha256=performance.get('pipeline_sha256'),
                                   source_sha256=performance.get('source_sha256'))
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        row['rejection_reasons'].append(f'artifact-unverified: {type(error).__name__}: {error}')
                    rows.append(row)
    return {'scope': 'Queue health AND hash-verified raw benchmark endpoint trust; no OCR quality inference. '
                     'Every attempt remains visible; accepted timing does not establish a privacy gate pass.',
            'queues': status, 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue-dir', type=Path, default=DEFAULT_STORAGE)
    parser.add_argument('--host', choices=('mac', 'linux'))
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    card = report(args.queue_dir, args.host)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(card, indent=2) + '\n')
    print('host   job / attempt                         fps    p95(s)  protected  idle(min) other(mean/max) trusted')
    for row in card['rows']:
        number = lambda value, digits=2: f'{value:.{digits}f}' if isinstance(value, (int, float)) else '-'
        protected = row.get('protected_fraction')
        print(f"{row['host']:6} {(row['job']+'/'+str(row['attempt']))[:36]:36} "
              f"{number(row.get('steady_fps')):>6} {number(row.get('steady_p95_seconds'),3):>8} "
              f"{number(100*protected if protected is not None else None):>9}% "
              f"{number(row.get('minimum_sampled_idle_percent')):>9}% "
              f"{number(row.get('mean_other_busy_percent'),1):>6}/{number(row.get('max_other_busy_percent'),1):<6} "
              f"{str(row['measurement_trusted']):>7}")
    for machine, state in card['queues'].items():
        counts = {name: sum(job['state'] == name for job in state['jobs'])
                  for name in sorted({job['state'] for job in state['jobs']})}
        print(machine, 'jobs:', json.dumps(counts), 'runner:', (state['runner'] or {}).get('state'))
    if args.out:
        print('Full joined receipt:', args.out)


if __name__ == '__main__':
    main()
