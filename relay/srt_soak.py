"""Root-queue-only SRT ingest soak; synthetic transport evidence, no OCR grade."""
import argparse
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import signal
import threading
import time

from relay.srt_capture import Capture
from relay.srt_fixture import mpegts
from relay.srt_replay import describe, publish
from relay.soak import Scenario, analyze_capture, require_queue_lease, write_json

ROOT = Path(__file__).resolve().parents[1]


class SRTScenario(Scenario):
    def _start(self, generation):
        stopped = self.context.Event()
        process = self.context.Process(target=publish, name=f'srt-replay-{generation}', args=(
            self.address.srt('publish', 'camera', self.phone), self.source,
            str(self.directory / f'publisher-{generation:02d}.json'), generation, stopped))
        process.start()
        item = (process, stopped, generation)
        self.processes.append(item)
        return item


def local_address():
    import socket
    from relay.security import RelayAddress
    with ExitStack() as stack:
        sockets = [stack.enter_context(socket.socket(socket.AF_INET, kind))
                   for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM, socket.SOCK_STREAM)]
        for sock in sockets:
            sock.bind(('127.0.0.1', 0))
        return RelayAddress('127.0.0.1', *[sock.getsockname()[1] for sock in sockets])


def source_rows():
    return {i: {'epoch_ms': 1700000000000, 'flash': i % 30 < 3} for i in range(360)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seconds', type=float, default=1200)
    parser.add_argument('--model-cache', required=True, type=Path)
    parser.add_argument('--tool-directory', required=True, type=Path)
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--fixture-sha256')
    parser.add_argument('--private-owner-fixture', action='store_true')
    parser.add_argument('--forced', action='store_true')
    parser.add_argument('--contended', action='store_true')
    args = parser.parse_args(argv)
    if not 20 <= args.seconds <= 1200:
        parser.error('--seconds must be 20..1200')
    if args.fixture and (not args.private_owner_fixture or not args.fixture_sha256):
        parser.error('Supplied owner fixture requires private provenance and exact hash')
    lease = require_queue_lease()
    if 'app-t3code-agents.slice' not in Path('/proc/self/cgroup').read_text():
        raise RuntimeError('SRT soak requires app-t3code-agents.slice')
    os.setpriority(os.PRIO_PROCESS, 0, 10)
    args.output.mkdir(parents=True, exist_ok=False)
    stopped = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stopped.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    summary = {'status': 'failed', 'quality': 'unqualified; trusted seal/OCR/scorer untouched',
               'timing_qualification': 'requires root queue diagnostics',
               'forced': args.forced or os.environ.get('IRL_SHIELD_PERF_QUEUE_FORCED') == '1',
               'contended': True if args.contended else None,
               'queue_attempt_receipt': os.environ.get('IRL_SHIELD_PERF_QUEUE_RECEIPT'),
               'queue_lease': lease, 'seconds_requested': args.seconds}
    scenario = capture = engine = None
    runtime_owns_engine = False
    started = time.monotonic()
    cleanup = []
    phase = 'source-prepare'
    try:
        if args.fixture:
            fixture = args.fixture.resolve()
            if not any(part in ('out', '.tmp') for part in fixture.parts):
                raise ValueError('Private owner media must remain under ignored out/ or .tmp/')
        else:
            fixture = args.output / 'synthetic.ts'
            fixture.write_bytes(mpegts(origin=10, frames=360, width=1280, height=720, timing=True))
        import cv2
        cv2.setNumThreads(1)
        source, _ = describe(fixture)
        if args.fixture_sha256 and source['sha256'] != args.fixture_sha256:
            raise ValueError('Owner fixture hash mismatch')
        source['license'] = ('owner-supplied/nonredistributable pending explicit license'
                             if args.fixture else 'CC0-1.0; original synthetic fixture')
        source['scope'] = 'PRIVATE internal diagnostic only' if args.fixture else 'synthetic functional transport only'
        write_json(args.output / 'source.json', source)
        phase = 'server-start'
        from relay.mediamtx import MediaMTX, verified_binary, linux_bound_sockets
        from relay.security import Credentials
        from relay.runtime import make_engine, run
        from relay.seal import sha256_file
        binary = verified_binary(args.tool_directory)
        address = local_address()
        phone, internal = Credentials.generate(), Credentials.generate()
        with MediaMTX(address, phone, internal, binary) as server:
            write_json(args.output / 'listeners.json', linux_bound_sockets(server.process.pid))
            scenario = SRTScenario(str(fixture), address, phone, args.output,
                                   args.seconds, server.process.pid, 'srt')
            phase = 'engine-start'
            engine = make_engine(args.model_cache, provider='cuda', faults=(scenario.plan['accurate_stall_pts'],))
            paths = [p for folder in ('relay', 'shield', 'bench') for p in (ROOT / folder).rglob('*.py')]
            write_json(args.output / 'provenance.json', {
                'source_sha256': {str(p.relative_to(ROOT)): sha256_file(p) for p in paths},
                'models': {p.name: sha256_file(p) for p in args.model_cache.glob('*.onnx')},
                'mediamtx_sha256': sha256_file(binary), 'queue_lease': lease,
                'fault_plan': scenario.plan, 'credentials': 'memory/private spawn pipe only'})
            capture = Capture(address.srt('read', 'shielded'), args.output / 'capture')
            phase = 'runtime'
            runtime_owns_engine = True
            summary['runtime'] = run(engine, address, phone, internal, args.output / 'runtime', stopped,
                                     args.seconds + 8, control_ready=scenario.ready)
            phase = 'workers-close'
            scenario.close()
            capture.close()
            summary['server_pid'] = server.process.pid
        summary['server_stopped'] = server.process.poll() is not None
        summary['faults'] = scenario.actual
        summary['publishers'] = scenario.exits
        summary['capture'] = dict(capture.stats)
        frames = [json.loads(line) for line in (args.output / 'runtime/frames.jsonl').read_text().splitlines()]
        release = scenario.actual.get('hold_release')
        after = [f for f in frames if release and f['encoded_at_monotonic'] >= release]
        summary['live_after_hold_release'] = sum(f['state'] == 'LIVE' and not f['slate'] for f in after)
        summary['hold_frames'] = sum(f['state'] == 'HOLD' for f in frames)
        summary['capture_analysis'] = []
        phase = 'capture-analysis'
        for segment in capture.segments:
            if not segment['bytes']:
                continue
            directory = args.output / f"analysis-{segment['generation']:04d}"
            directory.mkdir()
            os.link(capture.directory / segment['file'], directory / 'network.ts')
            summary['capture_analysis'].append(analyze_capture(directory, {} if args.fixture else source_rows()))
        if args.fixture:
            summary['av_offset'] = 'unmeasured: raw owner video has no independently identified flash/tone; no sync claim'
        analyses = summary['capture_analysis']
        hold = [f for f in frames if scenario.actual.get('hold_start', math.inf) + .25
                <= f['presented_at'] < scenario.actual.get('hold_release', -math.inf)]
        stall_start, stall_end = scenario.plan['accurate_stall_pts']
        stall = [f for f in frames if stall_start + 1 <= f['pts'] < stall_end]
        tail = [f for f in frames if f['encoded_at_monotonic'] >= frames[-1]['encoded_at_monotonic'] - 10] if frames else []
        checks = {
            'complete_runtime_duration': summary['runtime']['seconds'] >= args.seconds + 7,
            'complete_fault_schedule': set(scenario.actual) == {'hold_start', 'sender_kill', 'sender_reconnect', 'hold_release'},
            'controller_clean': not scenario.error,
            'publishers_reaped': all(e['stopped'] and (e['intentional_kill'] or e['exitcode'] == 0) for e in scenario.exits),
            'server_stopped': summary['server_stopped'],
            'reader_reconnected': summary['runtime']['session']['sessions'] >= 2 and summary['runtime']['session']['disconnections'] >= 1,
            'reader_queue_bounded': summary['runtime']['input_queue_high_water'] <= summary['runtime']['input_queue_capacity'],
            'hold_interval_protected': bool(hold) and all(f['slate'] and f['protected'] for f in hold),
            'stall_interval_protected': bool(stall) and all(f['protected'] for f in stall),
            'live_after_release': summary['live_after_hold_release'] > 0,
            'live_in_final_ten_seconds': any(f['state'] == 'LIVE' and not f['slate'] for f in tail),
            'network_bytes_received': capture.stats['packets'] > 0,
        }
        publisher = json.loads((args.output / 'publisher-02.json').read_text())
        checks['replacement_publisher_stopped_cleanly'] = publisher['status'] == 'stopped'
        checks.update({
            'independent_decoded_frame_count': sum(a['decoded_frames'] for a in analyses) >= math.ceil(args.seconds * 30),
            'independent_decoded_duration': sum(a['video_span_seconds'] + 1 / 30 for a in analyses) >= args.seconds,
            'independent_pts_continuity': bool(analyses) and all(not a['nonincreasing_video_pts'] and a['max_video_gap_seconds'] <= 2 / 30 for a in analyses),
            'independent_spatial_video_and_audio': bool(analyses) and all(a['spatial_content_frames'] > 0 and a['audio_samples'] > 0 for a in analyses),
        })
        if not args.fixture:
            checks['measured_network_av_offset'] = any(a['flash_beep_pairs'] for a in analyses)
        summary['checks'] = checks
        functional = all(checks.values())
        summary['status'] = 'functional-pass' if functional else 'failed'
    except Exception as error:
        summary['failure'] = {'phase': phase, 'error_class': type(error).__name__}
    finally:
        for name, worker in (('scenario', scenario), ('capture', capture),
                             ('engine', engine if not runtime_owns_engine else None)):
            if worker is not None:
                try:
                    worker.close()
                except Exception as error:
                    cleanup.append({'worker': name, 'error_class': type(error).__name__})
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        summary['cleanup_errors'] = cleanup
        summary['seconds_total'] = time.monotonic() - started
        if cleanup:
            summary['status'] = 'failed'
        write_json(args.output / 'summary.json', summary)
    print(json.dumps({'status': summary['status'], 'receipt': str(args.output / 'summary.json')}))
    return 0 if summary['status'] == 'functional-pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
