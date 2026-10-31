"""Require actual archive artifacts and describe observed denominators honestly."""
from collections import Counter
import json
from pathlib import Path

from .source import FPS, SECONDS, sha256


def local_dashboard(**kwargs):
    from shield.dashboard import DashboardServer
    class LocalDemoDashboard(DashboardServer):
        def _announce(self):
            # Automated loopback runs keep invitation/token in RAM; ordinary
            # DashboardServer retains its attended private-terminal behavior.
            pass
    return LocalDemoDashboard(**kwargs)


def check_archive(directory, sender_receipt):
    directory, sender_receipt = Path(directory), Path(sender_receipt)
    def nonempty(path):
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError('W8 rehearsal archive missing or empty')
        return path
    runtime_path = nonempty(directory / 'runtime.json')
    frames_path = nonempty(directory / 'frames.jsonl')
    nonempty(sender_receipt)
    runtime = json.loads(runtime_path.read_text())
    frames = [json.loads(line) for line in frames_path.read_text().splitlines()]
    sender = [json.loads(line) for line in sender_receipt.read_text().splitlines()]
    terminal = sender[-1]
    if (runtime['status'] != 'stopped' or runtime['cleanup_errors']
            or runtime.get('failure') or runtime['verified_tls'] is not None
            or runtime['output_frames'] != len(frames) or not frames
            or terminal.get('kind') != 'sender-end' or terminal.get('complete') is not True
            or terminal['packets'] != FPS * SECONDS):
        raise RuntimeError('W8 rehearsal output or single-pass publication incomplete')
    encoded = {}
    for generation in {row['egress_generation'] for row in frames}:
        name = 'encoded.flv' if generation == 1 else f'encoded-g{generation:04d}.flv'
        path = nonempty(directory / name)
        encoded[name] = sha256(path)
    live = sum(row['state'] == 'LIVE' and not row['slate'] and not row['protected'] for row in frames)
    if not live:
        raise RuntimeError('W8 rehearsal has no archived LIVE content')
    indices = {row['index'] for row in frames}
    first, stop = min(indices), max(indices) + 1
    report = {'schema': 'irl-shield-w8-local-observations-v1', 'status': 'NOT CLEARED',
        'runtime_sha256': sha256(runtime_path), 'frames_sha256': sha256(frames_path),
        'sender_sha256': sha256(sender_receipt), 'encoded_sha256': encoded,
        'denominator': 'Every row in frames.jsonl, including startup, protection and post-publisher output; no exclusions',
        'archived_outputs': len(frames), 'runtime_output_frames': runtime['output_frames'],
        'states': dict(Counter(row['state'] for row in frames)), 'live_non_slate_outputs': live,
        'observed_engine_index_window': [first, stop],
        'unarchived_engine_slots_within_window': stop - first - len(indices),
        'startup_engine_zero_outputs': sum(row['index'] == 0 for row in frames),
        'explicit_ingest_gap_outputs': sum(row['coverage']['reason'] == 'ingest-gap' for row in frames),
        'encoded_after_publisher_finished': sum(row['encoded_at_monotonic'] >= terminal['finished_at_monotonic'] for row in frames),
        'timing_note': 'Counts overlap. Publisher EOF does not establish last decoded input arrival or source identity.',
        'source_identity': None, 'native_packet_projection_proof': None,
        'limitations': 'No native content joins, model execution/projection attestation, decoded media quality or branding clearance. Encoded artifact presence is not decoded proof.'}
    (directory / 'rehearsal.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
