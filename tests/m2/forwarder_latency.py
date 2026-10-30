"""Queue-only loopback frame-write comparison, synthetic CC0 video/silence.

The direct legacy RTMPS baseline is deliberately test-only and loopback-only.
This measures client Egress.write overhead, not receiver arrival latency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
from relay.mediamtx import verified_binary
from relay.soak import require_queue_lease
from relay.stream import Egress
from relay.tls_forwarder import TLSForwarder
from shield.types import Coverage, PresentedFrame
from forwarder_probe import certificates, server, wait_witness


def quantiles(values):
    return {'p50_ms': float(np.quantile(values, .5)), 'p95_ms': float(np.quantile(values, .95))}


def trial(port, name, encoder, forwarded, cafile, log, process):
    forwarder = TLSForwarder('127.0.0.1', port, cafile=cafile) if forwarded else None
    if forwarder:
        forwarder.__enter__()
    endpoint = f'rtmp://127.0.0.1:{forwarder.port}' if forwarder else f'rtmps://127.0.0.1:{port}'
    output = None
    samples, startup = [], []
    try:
        start = time.monotonic()
        output = Egress((endpoint + '/app/' + name + '?bandwidthtest=true',), None,
                        width=1280, height=720, encoder=encoder)
        initialization = time.monotonic() - start
        y, x = np.indices((720, 1280))
        background = np.stack((x % 180 + 30, y % 180 + 30, (x // 7 + y // 7) % 180 + 30), axis=2).astype(np.uint8)
        pcm = np.zeros(1600, np.int16)
        mask = np.full((720, 1280), 255, np.uint8)
        origin = time.monotonic()
        late = 0
        for index in range(990):  # 3 seconds warmup + 30 seconds steady at 30fps.
            due = origin + index / 30
            time.sleep(max(0, due - time.monotonic()))
            pixels = background.copy()
            left = (index * 7) % 1216
            pixels[320:384, left:left + 64] = 240
            now = time.monotonic()
            frame = PresentedFrame(index, index / 30, pixels, mask, [],
                Coverage(0, 0, True, 'synthetic'), 'LIVE', now, now, False, False)
            began = time.perf_counter_ns()
            accepted = output.write(frame, pcm)
            elapsed = (time.perf_counter_ns() - began) / 1e6
            if accepted is False:
                raise RuntimeError('Loopback timing destination refused a frame')
            (startup if index < 90 else samples).append(elapsed)
            if index >= 90 and time.monotonic() > due + 1 / 30:
                late += 1
        time.sleep(max(0, origin + 33 - time.monotonic()))
        duration = time.monotonic() - (origin + 3)
        wait_witness(log, name, process)
        return {'path': 'verified-forwarder' if forwarded else 'legacy-direct-loopback-baseline',
                'initialization_seconds': initialization, 'warmup_frames': 90,
                'warmup': quantiles(startup), 'steady_frames': len(samples),
                'steady_seconds': duration, 'writes_over_source_period': late,
                'steady': quantiles(samples), 'samples_ms': samples}
    finally:
        try:
            if output:
                output.close()
        finally:
            if forwarder:
                forwarder.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--encoder', choices=('h264_nvenc', 'libx264'), default='h264_nvenc')
    args = parser.parse_args()
    require_queue_lease()
    args.out.mkdir(parents=True, exist_ok=False)
    rows = []
    with tempfile.TemporaryDirectory(prefix='irl-shield-tls-latency-') as temporary:
        root = certificates(Path(temporary))
        with server(verified_binary(), root, args.out) as (peer, port, log):
            for repetition in range(5):
                # Paired alternating order reduces startup/order bias.
                for forwarded in ((False, True) if repetition % 2 == 0 else (True, False)):
                    name = f'trial-{repetition}-' + ('forwarded' if forwarded else 'baseline')
                    row = trial(port, name, args.encoder, forwarded, root / 'peer.crt', log, peer)
                    row['repetition'] = repetition
                    rows.append(row)
                    (args.out / 'partial.json').write_text(json.dumps(rows, indent=2) + '\n')
    baseline = [r for r in rows if r['path'].startswith('legacy')]
    forwarded = [r for r in rows if r['path'].startswith('verified')]
    compare = {}
    for metric in ('p50_ms', 'p95_ms'):
        direct = [r['steady'][metric] for r in baseline]
        verified = [r['steady'][metric] for r in forwarded]
        compare[metric] = {'baseline_median_of_5': float(np.median(direct)),
                          'forwarder_median_of_5': float(np.median(verified)),
                          'paired_delta_median_of_5': float(np.median([verified[i] - direct[i] for i in range(5)]))}
    files = ('relay/tls_forwarder.py', 'relay/stream.py', 'tests/m2/forwarder_latency.py', 'tests/m2/forwarder_probe.py')
    report = {'scope': 'Egress.write client-call overhead; not end-to-end delivery latency or relay FPS qualification',
              'encoder': args.encoder, 'shape': [1280, 720], 'source_fps': 30, 'repetitions_per_path': 5,
              'forced': __import__('os').environ.get('IRL_SHIELD_PERF_QUEUE_FORCED') == '1',
              'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
              'comparison': compare, 'trials': rows}
    (args.out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'scope': report['scope'], 'comparison': compare}, indent=2))


if __name__ == '__main__':
    main()
