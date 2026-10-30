"""Select one sealed measurement by queue trust, then grade held-out once.

No models/datasets/dependencies are introduced. Real grading uses the existing
three judges and immutable cross_host validation. Queue this AFTER timed jobs;
all media remain benchmark-only, without audio or demo-readiness claims.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from bench.perf_queue import Queue, atomic_json, file_lock
from bench.perf_queue_report import queue_attempt_clean

ROOT = Path(__file__).resolve().parents[1]


def artifact_bytes(artifact):
    path = Path(artifact['path'])
    data = path.read_bytes()
    if (not artifact.get('exists') or len(data) != artifact.get('bytes')
            or hashlib.sha256(data).hexdigest() != artifact.get('sha256')):
        raise ValueError('Measurement plan hash/size differs from queue receipt')
    return data


def finish_once(queue_dir, job_id, final_dir, *, grade=None):
    """Grade the first clean complete attempt, or the last contended complete one.

    `grade` is the sealed-measurement grading seam: production uses cross_host;
    synthetic adapters test selection/once-only behavior without claiming OCR.
    """
    final_dir = Path(final_dir)
    final_dir.mkdir(parents=True, exist_ok=True)
    destination = final_dir / 'scorecard.json'
    with file_lock(final_dir / '.grade.lock'):
        if destination.exists():
            existing = json.loads(destination.read_text())
            if existing.get('measurement_queue_job_id') != job_id:
                raise ValueError('Existing held-out card belongs to a different measurement job')
            trust = existing['queue_measurement_trust']
            for key, identity in (('receipt', 'receipt_sha256'),
                                  ('measurement_plan', 'measurement_plan_sha256')):
                if hashlib.sha256(Path(trust[key]).read_bytes()).hexdigest() != trust[identity]:
                    raise ValueError('Already scored retained measurement changed')
            return existing
        queue = Queue(queue_dir)
        matches = [job for job in queue.jobs('mac') if job['id'] == job_id]
        if len(matches) != 1:
            raise ValueError('Exactly one queued Mac held-out measurement is required')
        job = matches[0]
        if job['state'] in ('pending', 'running'):
            raise RuntimeError('Measurement retries are not finished; no held-out judging started')
        candidates = []
        for receipt_path in job['attempts']:
            receipt_path = Path(receipt_path)
            receipt = json.loads(receipt_path.read_text())
            if receipt.get('phase') != 'closed':
                continue
            for artifact in receipt.get('receipts', []):
                if Path(artifact['path']).name != 'measurement-plan.json' or not artifact.get('exists'):
                    continue
                artifact_bytes(artifact)
                candidates.append((queue_attempt_clean(receipt), Path(artifact['path']), receipt_path, receipt))
        if not candidates:
            raise RuntimeError('No complete sealed held-out measurement; no quality verdict exists')
        selected = next((row for row in candidates if row[0]), candidates[-1])
        clean, plan_path, queue_path, attempt = selected
        if grade is None:
            from bench.cross_host import grade as grade_measurement, verify_measurement
            verified = verify_measurement(plan_path)
            cached = plan_path.parent / 'scorecard.json'
            if cached.exists():
                # A previous attempt may have completed OCR before the final copy.
                card = json.loads(cached.read_text())
                if (card.get('measurement_plan_sha256') != hashlib.sha256(plan_path.read_bytes()).hexdigest()
                        or card.get('pipeline_sha256') != verified['pipeline_sha256']):
                    raise ValueError('Already graded card differs from selected sealed measurement')
            else:
                card = grade_measurement(plan_path)
        else:
            card = grade(plan_path)
        card = deepcopy(card)
        if card.get('split') != 'heldout':
            raise ValueError('This command only finalizes the held-out split')
        card['measurement_queue_job_id'] = job_id
        card['queue_measurement_trust'] = {
            'clean': clean, 'receipt': str(queue_path),
            'receipt_sha256': hashlib.sha256(queue_path.read_bytes()).hexdigest(),
            'measurement_plan': str(plan_path),
            'measurement_plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            'selection': 'First clean complete sealed attempt, otherwise last complete contended attempt; no OCR or privacy score used in selection',
            'measurement_attempts': len(job['attempts']),
            'grading_once_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'grading_scope': 'Grading is outside every measurement clock; grading-job CPU contamination cannot validate a contended measurement'}
        card['gate_1']['queue_clean'] = clean
        card['gate_1']['queue_environment'] = clean
        for key in ('throughput', 'latency'):
            card['gate_1'][key] = card['gate_1'][key] and clean
        card['gate_1']['pass'] = all(value for key, value in card['gate_1'].items() if key != 'pass')
        card['scope'] += ' Final held-out measurement selected by queue trust before OCR; evaluated once, with queue trust required for performance acceptance.'
        atomic_json(destination, card)
        atomic_json(final_dir.parent / 'scorecard.json', card)
        return card


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue-dir', type=Path, required=True)
    parser.add_argument('--measurement-job-id', required=True)
    parser.add_argument('--final-dir', type=Path, default=ROOT / 'out/m1-heldout-final')
    args = parser.parse_args()
    card = finish_once(args.queue_dir, args.measurement_job_id, args.final_dir)
    print(json.dumps({key: card.get(key) for key in ('run_id', 'scope', 'natural', 'synthetic',
                      'masked_area_fraction', 'protected_fraction', 'gate_1', 'baseline_deltas',
                      'queue_measurement_trust')}, indent=2), flush=True)


if __name__ == '__main__':
    main()
