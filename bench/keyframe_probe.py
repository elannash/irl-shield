#!/usr/bin/env python3
"""Root-run synthetic regression; preparing this file does not exercise media.

Original synthetic inputs are CC0. Runtime dependencies are existing project
PyAV/FFmpeg/libx264 and NumPy; no new dependencies or production hooks.
"""
import argparse
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import select
import subprocess
import socket
import sys
import tempfile
import threading
import time

FPS = 30
SECONDS = 12
CASES = ('w8b', 'synthetic', 'phone')
LEASE_ENV = 'IRL_SHIELD_PERF_QUEUE_LEASE_FD'
NATIVE_ENV = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS')


def require(condition, code):
    if not condition:
        raise AssertionError(code)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    with Path(path).open('x') as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write('\n')


def native(root):
    require(sys.version_info[:2] == (3, 11), 'sdk-python-3.11-required')
    require(os.getpriority(os.PRIO_PROCESS, 0) == 10, 'inherited-nice10-required')
    require(all(os.environ.get(key) == '2' for key in NATIVE_ENV), 'native-thread-env2-required')
    require(os.environ.get('OPENCV_FOR_THREADS_NUM') == '1', 'opencv-env1-required')
    require(sys.dont_write_bytecode, 'python-B-required')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    sys.path.insert(0, str(root))
    from tools.demo_renderer.lease import inherited_exclusive
    fd = inherited_exclusive()
    import av
    import numpy as np
    av.logging.set_level(None)
    return av, np, fd


def scratch(path):
    path = Path(path).resolve()
    base = Path(tempfile.gettempdir()).resolve() / 'agents' / 'irl-shield'
    require(path.is_relative_to(base) and path != base, 'os-scratch-descendant-required')
    return path


def nals(data, framing, length_size=4):
    """Framing is explicit: MP4 avcC lengths versus RTSP Annex B."""
    if framing == 'avcc':
        result, cursor = [], 0
        while cursor < len(data):
            require(cursor + length_size <= len(data), 'avcc-truncated-length')
            size = int.from_bytes(data[cursor:cursor + length_size], 'big')
            cursor += length_size
            require(size > 0 and cursor + size <= len(data), 'avcc-truncated-nal')
            result.append(data[cursor:cursor + size])
            cursor += size
        return result
    starts = list(re.finditer(b'\x00\x00\x00?\x01', data))
    require(starts and starts[0].start() == 0, 'annexb-missing-start')
    result = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(data)
        # Preserve every payload byte; no trailing-zero compatibility trimming.
        nal = data[start.end():end]
        require(nal, 'annexb-empty-nal')
        result.append(nal)
    return result


def packet_row(packet, framing, length_size=4):
    units = nals(bytes(packet), framing, length_size)
    vcl = [unit for unit in units if 1 <= unit[0] & 31 <= 5]
    # Length prefix every NAL in the digest, preserving slice boundaries/order.
    digest = hashlib.sha256()
    for unit in vcl:
        digest.update(len(unit).to_bytes(4, 'big'))
        digest.update(unit)
    return {'pts': str(packet.pts * packet.time_base) if packet.pts is not None else None,
            'packet_bytes': packet.size,
            'nal_types': [unit[0] & 31 for unit in units],
            'nal_bytes': [len(unit) for unit in units],
            'vcl_slices': len(vcl), 'vcl_bytes': sum(map(len, vcl)),
            'vcl_sha256': digest.hexdigest(), 'idr': any(unit[0] & 31 == 5 for unit in vcl)}


def pixels(frame):
    image = frame.to_ndarray(format='bgr24')
    return {'full': hashlib.sha256(image.tobytes()).hexdigest(),
            'lower': hashlib.sha256(image[image.shape[0] // 2:].tobytes()).hexdigest()}


def codec_setup(stream):
    stream.codec_context.thread_count = 2
    stream.codec_context.thread_type = 'SLICE'


def direct_reference(av, video, evidence=None):
    packets, frames = [], {}
    with av.open(str(video)) as source:
        stream = source.streams.video[0]
        codec_setup(stream)
        extra = stream.codec_context.extradata
        require(extra and extra[0] == 1 and len(extra) >= 5, 'source-avcc-required')
        length_size = (extra[4] & 3) + 1
        for packet in source.demux(stream):
            if packet.dts is None:
                continue
            require(packet.pts == packet.dts, 'source-no-b-frames-required')
            pts = packet.pts * packet.time_base
            if pts >= SECONDS:
                break
            row = packet_row(packet, 'avcc', length_size)
            require(row['vcl_slices'] > 0, 'source-empty-vcl')
            row['index'] = len(packets)
            packets.append(row)
            for frame in packet.decode():
                require(frame.pts is not None, 'source-frame-pts-required')
                frames[str(frame.pts * frame.time_base)] = pixels(frame)
                if evidence is not None and frame.key_frame:
                    frame.to_image().save(evidence / f'source-key-{int(frame.pts * frame.time_base * FPS):04d}.png')
        for frame in stream.codec_context.decode(None):
            require(frame.pts is not None, 'source-drain-pts-required')
            frames[str(frame.pts * frame.time_base)] = pixels(frame)
    require(len(packets) == FPS * SECONDS, 'source-window-packet-count')
    require([Fraction(row['pts']) for row in packets] == [Fraction(i, FPS) for i in range(FPS * SECONDS)],
            'source-window-clock')
    require(set(frames) == {row['pts'] for row in packets}, 'source-decode-coverage')
    require(len({value['full'] for value in frames.values()}) == len(frames), 'source-identities-not-distinct')
    for row in packets:
        row['pixels'] = frames[row['pts']]
    return packets


def make_fixture(av, np, path, case):
    """One deterministic recipe per case. Guards measure, never auto-retune."""
    width, height, gop = (768, 512, 30) if case == 'synthetic' else (1280, 720, 60)
    rng = np.random.default_rng(20261030)
    base = rng.integers(0, 256, (height, width), dtype=np.uint8)
    options = {'preset': 'ultrafast', 'x264-params':
               f'keyint={gop}:min-keyint={gop}:scenecut=0:bframes=0:slices=4:threads=2'}
    if case == 'synthetic':
        options['crf'] = '0'
    else:
        options['x264-params'] += ':vbv-maxrate=5000:vbv-bufsize=10000:nal-hrd=cbr:force-cfr=1'
    with av.open(str(path), 'w') as output:
        stream = output.add_stream('libx264', rate=FPS, options=options)
        stream.width, stream.height, stream.pix_fmt = width, height, 'yuv420p'
        stream.codec_context.thread_count = 2
        stream.codec_context.max_b_frames = 0
        stream.gop_size = gop
        if case == 'phone':
            stream.bit_rate = 5_000_000
        for index in range(FPS * SECONDS):
            luma = base.copy() if case == 'synthetic' else np.roll(base, (index * 2, index * 3), (0, 1))
            if case == 'phone':
                # Temporal texture forces real VCL bitrate; filler cannot meet the guard.
                luma[height // 3:2 * height // 3] = rng.integers(
                    0, 256, (height // 3, width), dtype=np.uint8)
            for bit in range(9):
                value = 235 if index & (1 << bit) else 16
                x = 8 + bit * 18
                luma[8:24, x:x + 16] = value
                luma[height - 24:height - 8, x:x + 16] = value
            x = (index * 7) % (width - 24)
            luma[height // 2:height // 2 + 16, x:x + 16] = 235
            planar = np.full((height * 3 // 2, width), 128, dtype=np.uint8)
            planar[:height] = luma
            frame = av.VideoFrame.from_ndarray(planar, format='yuv420p')
            frame.pts, frame.time_base = index, Fraction(1, FPS)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode(None):
            output.mux(packet)
    return {'width': width, 'height': height, 'gop_frames': gop, 'options': options,
            'seed': 20261030, 'license': 'CC0-1.0', 'audio': False}


def validate_shape(case, rows):
    idrs = [row for row in rows if row['idr']]
    require(len(idrs) >= 3, 'at-least-three-source-idrs-required')
    if case == 'synthetic':
        require(all(row['vcl_slices'] >= 2 for row in idrs), 'synthetic-multiple-idr-slices-required')
        require(all(480_000 <= row['vcl_bytes'] <= 780_000 for row in idrs),
                'synthetic-measured-idr-outside-approximately-600KB')
    if case == 'w8b':
        require(max(row['vcl_bytes'] for row in idrs) >= 240_000, 'w8b-missing-large-idr')
    if case == 'phone':
        require([row['index'] for row in idrs] == list(range(0, FPS * SECONDS, 60)), 'phone-two-second-gop')
        bitrate = sum(row['vcl_bytes'] for row in rows) * 8 / SECONDS
        require(4_000_000 <= bitrate <= 6_000_000, 'phone-measured-vcl-bitrate-outside-4-to-6Mbps')
    return {'idr_vcl_bytes': [row['vcl_bytes'] for row in idrs],
            'idr_vcl_slices': [row['vcl_slices'] for row in idrs],
            'video_packet_bps': sum(row['packet_bytes'] for row in rows) * 8 / SECONDS,
            'vcl_bps': sum(row['vcl_bytes'] for row in rows) * 8 / SECONDS}


def prepare(args, av, np):
    directory = scratch(args.fixtures)
    directory.mkdir(parents=True, exist_ok=False)
    from tools.demo_renderer.sender import source_manifest
    expected = args.root / 'out/w8b/occluded-render-01/source.json'
    video, _ = source_manifest(expected)
    sources = {'w8b': video}
    recipes = {}
    for case in ('synthetic', 'phone'):
        sources[case] = directory / f'{case}.mp4'
        recipes[case] = make_fixture(av, np, sources[case], case)
    report = {'schema': 'queue-regression-fixtures-v1', 'created_at_monotonic': time.monotonic(),
              'w8b_manifest': str(expected), 'w8b_manifest_sha256': sha(expected),
              'cases': {}, 'actual_argv': sys.argv, 'measured': True}
    for case in CASES:
        evidence = directory / f'{case}-direct-keyframes'
        evidence.mkdir()
        rows = direct_reference(av, sources[case], evidence)
        # Persist failed measurements too. A failed guard never yields a usable seal.
        write_json(directory / f'{case}-reference.json', rows)
        report['cases'][case] = {'video': str(sources[case]), 'video_sha256': sha(sources[case]),
                                 'reference_sha256': sha(directory / f'{case}-reference.json'),
                                 'recipe': recipes.get(case), 'measurements': {
                                     'idr_vcl_bytes': [row['vcl_bytes'] for row in rows if row['idr']],
                                     'vcl_bps': sum(row['vcl_bytes'] for row in rows) * 8 / SECONDS}}
    write_json(directory / 'measurements.json', report)
    for case in CASES:
        validate_shape(case, json.loads((directory / f'{case}-reference.json').read_text()))
    write_json(directory / 'fixtures.json', report)


class LogTap:
    def __init__(self, stream, owner):
        self.stream, self.owner, self.oversized = stream, owner, False

    def readline(self, size=-1):
        raw = self.stream.readline(size)
        if len(raw) > 8192 or self.oversized:
            self.oversized = not raw.endswith(b'\n')
            self.owner.observer_drops += 1
        elif raw:
            line = raw.decode('utf-8', errors='replace')
            code = None
            if '[RTMP]' in line and "is publishing to path 'camera'" in line:
                code = 'camera-publishing'
                self.owner.publishing.set()
            if 'reader is too slow' in line:
                code = 'slow-reader-warning'
                self.owner.slow_warnings += 1
            elif 'write queue is full' in line:
                code = 'write-queue-full-warning'
            elif ' WAR ' in line:
                code = 'other-warning'
            if code and code.endswith('warning'):
                self.owner.observer_warning_counts[code] = self.owner.observer_warning_counts.get(code, 0) + 1
            if code:
                if len(self.owner.observed) < 256:
                    self.owner.observed.append({'code': code, 'at_monotonic': time.monotonic()})
                else:
                    self.owner.observer_drops += 1
        return raw

    def __getattr__(self, name):
        return getattr(self.stream, name)


def observer_class(base):
    class ObservedMediaMTX(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.publishing = threading.Event()
            self.observed = []
            self.observer_warning_counts = {}
            self.slow_warnings = self.observer_drops = 0

        def _diagnostics(self):
            original = self.process.stdout
            self.process.stdout = LogTap(original, self)
            try:
                # Production's safe drain/classifications still consume every raw line.
                super()._diagnostics()
            finally:
                self.process.stdout = original
    return ObservedMediaMTX


def publish_worker(av):
    """Exec-spawned publisher. Read synthetic endpoint over a private stdin pipe."""
    config = json.loads(sys.stdin.buffer.readline(16385))
    terminal = {'complete': False, 'packets': 0, 'code': 'sender-start'}
    try:
        with av.open(config['video']) as source:
            incoming = source.streams.video[0]
            with av.open(config['url'], 'w', format='flv', timeout=(3., 3.)) as output:
                outgoing = output.add_stream_from_template(incoming)
                started = time.monotonic()
                for packet in source.demux(incoming):
                    if packet.dts is None:
                        continue
                    require(packet.pts == packet.dts, 'publisher-no-b-frames')
                    pts = packet.pts * packet.time_base
                    if pts >= SECONDS:
                        break
                    require(pts == Fraction(terminal['packets'], FPS), 'publisher-clock')
                    delay = max(0., started + float(pts) - time.monotonic())
                    if select.select([sys.stdin], [], [], delay)[0]:
                        break  # Parent closing its private control pipe requests stop.
                    packet.stream = outgoing
                    output.mux(packet)
                    terminal['packets'] += 1
                if terminal['packets'] == FPS * SECONDS:
                    write_json(config['sent_receipt'], {'complete': True, 'packets': terminal['packets']})
                    # Closing a publisher also tears down RTSP readers. Keep the
                    # connection alive until the parent has decoded the window.
                    select.select([sys.stdin], [], [], 5.)
        terminal['complete'] = terminal['packets'] == FPS * SECONDS
        terminal['code'] = 'sender-complete' if terminal['complete'] else 'sender-incomplete'
    except BaseException:
        terminal['code'] = 'sender-failed-private-diagnostics-suppressed'
    finally:
        write_json(config['receipt'], terminal)
    if not terminal['complete']:
        raise SystemExit(2)


def stop_child(process):
    if process.stdin is not None and not process.stdin.closed:
        process.stdin.close()
    forced = False
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        forced = True
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    return {'pid': process.pid, 'exitcode': process.returncode,
            'forced': forced, 'survived': process.poll() is None}


def pull(av, url, receipt, directory, last_vcl_sha256):
    packets, frames, parameters, terminal, errors = [], [], [], 'not-opened', []
    opened_at = time.monotonic()
    with av.open(url, timeout=(4., 2.), container_options={
            'rtsp_transport': 'tcp', 'probesize': '32768', 'analyzeduration': '100000',
            'rw_timeout': '2000000'}) as incoming:
        stream = incoming.streams.video[0]
        codec_setup(stream)
        try:
            terminal = 'demux-eof'
            for packet in incoming.demux(stream):
                require(time.monotonic() - opened_at <= SECONDS + 10, 'rtsp-wall-time-bound')
                if not packet.size:
                    continue  # Explicit codec finish below owns the flush.
                row = packet_row(packet, 'annexb')
                if row['vcl_slices']:
                    packets.append(row)
                else:
                    parameters.append({**row, 'payload_sha256': hashlib.sha256(bytes(packet)).hexdigest()})
                require(len(packets) <= FPS * SECONDS + 4, 'rtsp-packet-bound')
                for frame in packet.decode():
                    frames.append({'pts': str(frame.pts * frame.time_base) if frame.pts is not None else None,
                                   'pixels': pixels(frame)})
                    # Retain independent before-mask evidence for the root's lower-image eye.
                    if frame.key_frame:
                        image = directory / f'rtsp-key-{len(frames):04d}.png'
                        frame.to_image().save(image)
                        frames[-1]['key_image'] = image.name
                        frames[-1]['key_image_sha256'] = sha(image)
                if row['vcl_slices'] and row['vcl_sha256'] == last_vcl_sha256:
                    terminal = 'source-window-complete'
                    break
        except av.error.FFmpegError as error:
            code = type(error).__name__
            # MTX can leave the session open after publisher EOF. Only a completed
            # publisher plus full tail coverage can later make this terminal normal.
            complete = receipt.exists() and json.loads(receipt.read_text()).get('complete') is True
            terminal = 'publisher-complete-idle' if complete and code in ('ExitError', 'TimeoutError', 'EOFError') else 'decode-error'
            if terminal == 'decode-error':
                errors.append({'code': 'decoder-ffmpeg-error', 'error_class': code})
        except Exception as error:
            terminal = 'decoder-or-evidence-error'
            errors.append({'code': str(error) if isinstance(error, AssertionError) else 'decoder-or-evidence-error',
                           'error_class': type(error).__name__})
        finally:
            try:
                for frame in stream.codec_context.decode(None):
                    frames.append({'pts': str(frame.pts * frame.time_base) if frame.pts is not None else None,
                                   'pixels': pixels(frame), 'drained': True})
            except av.error.FFmpegError as error:
                errors.append({'code': 'decoder-finish-error', 'error_class': type(error).__name__})
    return {'packets': packets, 'frames': frames, 'parameter_packets': parameters,
            'terminal': terminal, 'errors': errors,
            'opened_at_monotonic': opened_at, 'finished_at_monotonic': time.monotonic()}


def assess(source, received):
    packets, frames = received['packets'], received['frames']
    failures = []
    def check(condition, code):
        if not condition:
            failures.append(code)
    check(bool(packets) and bool(frames), 'nonempty-independent-receive-required')
    by_digest = {}
    for row in source:
        by_digest.setdefault(row['vcl_sha256'], []).append(row)
    anchors = [(row, by_digest[row['vcl_sha256']][0]) for row in packets
               if row['pts'] is not None and len(by_digest.get(row['vcl_sha256'], [])) == 1]
    check(len(anchors) >= 2, 'at-least-two-unique-intact-vcl-clock-anchors')
    if len(anchors) < 2:
        return {'failures': failures, 'clock_offset': None, 'associated': []}
    # Source FLV timestamps have millisecond rounding; RTSP has 90kHz ticks.
    # Establish identity ONLY with complete exact VCL, then associate independently
    # by a single constant offset within 2ms, far below a 33ms frame interval.
    offsets = sorted(Fraction(a['pts']) - Fraction(b['pts']) for a, b in anchors)
    offset = offsets[len(offsets) // 2]
    tolerance = Fraction(2, 1000)
    check(all(abs(value - offset) <= tolerance for value in offsets), 'inconsistent-clock-anchors')
    def identity(pts):
        if pts is None:
            return None
        candidates = [row for row in source if abs(Fraction(pts) - offset - Fraction(row['pts'])) <= tolerance]
        return candidates[0] if len(candidates) == 1 else None
    associated, packet_ids, frame_ids, idrs = [], [], [], []
    for row in packets:
        exact_candidates = by_digest.get(row['vcl_sha256'], [])
        original = exact_candidates[0] if len(exact_candidates) == 1 else identity(row['pts'])
        if original is None:
            failures.append('rtsp-packet-unassociated')
            continue
        index = original['index']
        packet_ids.append(index)
        exact = row['vcl_sha256'] == original['vcl_sha256']
        check(exact, f'wrong-vcl-bytes-source-{index}')
        associated.append({'source_index': index, 'received_pts': row['pts'], 'vcl_equal': exact,
                           'association': 'unique-complete-vcl' if len(exact_candidates) == 1 else 'anchored-clock'})
        if original['idr']:
            idrs.append(index)
    for row in frames:
        original = identity(row['pts'])
        if row['pts'] is None:
            matches = [item for item in source if item['pixels']['full'] == row['pixels']['full']]
            original = matches[0] if len(matches) == 1 else None
        if original is None:
            failures.append('rtsp-frame-unassociated')
            continue
        index = original['index']
        frame_ids.append(index)
        check(row['pixels']['full'] == original['pixels']['full'], f'wrong-full-pixels-source-{index}')
        check(row['pixels']['lower'] == original['pixels']['lower'], f'wrong-lower-pixels-source-{index}')
    # Discard no observed corruption; coverage may start at the first joined IDR.
    check(len(set(idrs[1:])) >= 2, 'two-postjoin-idrs-required')
    check(len(set(row['pixels']['full'] for row in frames)) >= 3, 'distinct-decoded-identities-required')
    if idrs:
        expected = list(range(idrs[0], len(source)))
        check([index for index in packet_ids if index >= idrs[0]] == expected,
              'complete-contiguous-vcl-tail-required')
        check(frame_ids == expected, 'complete-contiguous-decoded-tail-required')
    else:
        failures.append('no-received-idr')
    check(not received['errors'], 'decoder-error-or-finish-error')
    return {'failures': failures, 'clock_offset': str(offset), 'clock_tolerance': str(tolerance),
            'unique_intact_vcl_anchors': len(anchors), 'received_idr_indices': idrs,
            'associated': associated}


def run_case(args, case, fixture, av, fd):
    from relay.mediamtx import MediaMTX
    from relay.security import Credentials, RelayAddress, mediamtx_environment
    from tools.demo_renderer.sender import endpoint
    directory = scratch(args.results) / case
    directory.mkdir()
    item = fixture['cases'][case]
    video = Path(item['video'])
    source = json.loads((scratch(args.fixtures) / f'{case}-reference.json').read_text())
    require(sha(video) == item['video_sha256'], 'immutable-source-seal-mismatch')
    require(sha(scratch(args.fixtures) / f'{case}-reference.json') == item['reference_sha256'], 'reference-seal-mismatch')
    shape = validate_shape(case, source)
    # Fresh direct decoding checks the persisted reference before opening the relay.
    require(direct_reference(av, video) == source, 'direct-reference-recheck-mismatch')
    phone, internal = Credentials.generate(), Credentials.generate()
    with ExitStack() as reservations:
        sockets = [reservations.enter_context(socket.socket(socket.AF_INET, kind))
                   for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM, socket.SOCK_STREAM)]
        for reservation in sockets:
            reservation.bind(('127.0.0.1', 0))
        address = RelayAddress('127.0.0.1', *(s.getsockname()[1] for s in sockets))
    queue = mediamtx_environment(address, phone, internal)['MTX_WRITEQUEUESIZE']
    require(queue in ('128', '1024'), 'product-queue-must-be-old128-or-candidate1024')
    observed_type = observer_class(MediaMTX)
    server = observed_type(address, phone, internal)
    sender_receipt = directory / 'publisher.json'
    sent_receipt = directory / 'publisher-sent.json'
    sender = None
    result = {'case': case, 'queue_from_actual_product_config': queue, 'measurements': shape,
              'actual_argv': sys.argv, 'source_sha256_before': sha(video), 'received': None,
              'public_verdict': 'RED', 'failures': [], 'eye_verdict': None,
              'physical': {'parent_pid': os.getpid(), 'sender': None, 'mtx': None},
              'product_sources': {name: sha(args.root / name) for name in ('relay/mediamtx.py', 'relay/security.py')}}
    started = False
    try:
        with server:
            try:
                result['physical']['mtx'] = {'pid': server.process.pid}
                sender = subprocess.Popen([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
                    'publish', '--root', str(args.root), '--fixtures', str(args.fixtures)],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, pass_fds=(fd,))
                started = True
                sender.stdin.write((json.dumps({'video': str(video),
                    'url': endpoint(address, phone, local_only=True), 'receipt': str(sender_receipt),
                    'sent_receipt': str(sent_receipt)}) + '\n').encode())
                sender.stdin.flush()
                require(server.publishing.wait(5), 'no-real-camera-publication-witness')
                require(sender.poll() is None, 'publisher-died-before-rtsp-open')
                result['publication_witness'] = list(server.observed)
                result['received'] = pull(av, address.rtsp('camera', internal), sent_receipt,
                                          directory, source[-1]['vcl_sha256'])
                verdict = assess(source, result['received'])
                result['assessment'] = verdict
                result['failures'].extend(verdict['failures'])
            finally:
                if started:
                    result['physical']['sender'] = stop_child(sender)
                    started = False
    except BaseException as error:
        # Only our fixed assertions are safe. Native exception text may carry URLs.
        result['failures'].append(str(error) if isinstance(error, AssertionError) else f'run-{type(error).__name__}')
    finally:
        if started:
            result['physical']['sender'] = stop_child(sender)
        result['physical']['mtx'] = {'pid': server.process.pid if server.process else None,
            'exitcode': server.process.poll() if server.process else None,
            'diagnostic_thread_alive': bool(server._diagnostic_thread and server._diagnostic_thread.is_alive())}
        result['diagnostics'] = {'slow_warning_count': server.slow_warnings, 'observer_drops': server.observer_drops,
            'warning_counts': server.observer_warning_counts,
            'production_warning_counts': dict(getattr(server, 'warning_counts', {})),
            'production_write_queue_size': getattr(server, '_write_queue_size', None),
            'events': server.observed, 'production_close_events': list(server.close_events),
            'production_diagnostic_drops': server.diagnostic_drops}
        result['source_sha256_after'] = sha(video)
        if sender_receipt.exists():
            result['publisher'] = json.loads(sender_receipt.read_text())
        if result['source_sha256_after'] != result['source_sha256_before']:
            result['failures'].append('immutable-source-changed')
        if server.observer_warning_counts.get('write-queue-full-warning', 0):
            result['failures'].append('write-queue-full-warnings')
        if server.slow_warnings:
            result['failures'].append('reader-is-too-slow-warnings')
        if server.observer_drops or server.diagnostic_drops:
            result['failures'].append('diagnostic-retention-loss')
        owned_sender = result['physical']['sender']
        if not owned_sender or owned_sender['exitcode'] != 0 or owned_sender['forced'] or owned_sender['survived']:
            result['failures'].append('publisher-clean-complete-exit-required')
        if result['physical']['mtx']['exitcode'] is None or result['physical']['mtx']['diagnostic_thread_alive']:
            result['failures'].append('mediamtx-clean-reap-required')
        if not result.get('publisher', {}).get('complete'):
            result['failures'].append('publisher-complete-receipt-required')
        if not result['failures']:
            result['public_verdict'] = 'PIXELS_AND_VCL_GREEN_EYE_PENDING'
        write_json(directory / 'result.json', result)
    require(not result['failures'], 'public-regression-failed-see-preserved-result')
    return result['public_verdict']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run', 'publish'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--results', type=Path)
    args = parser.parse_args()
    args.root = args.root.resolve()
    av, np, fd = native(args.root)
    if args.mode == 'publish':
        publish_worker(av)
        return
    if args.mode == 'prepare':
        prepare(args, av, np)
        return
    require(args.results is not None, 'fresh-results-directory-required')
    directory = scratch(args.results)
    directory.mkdir(parents=True, exist_ok=False)
    fixture = json.loads((scratch(args.fixtures) / 'fixtures.json').read_text())
    from tools.demo_renderer.sender import source_manifest
    video, _ = source_manifest(args.root / 'out/w8b/occluded-render-01/source.json')
    require(str(video) == fixture['cases']['w8b']['video'], 'original-w8b-path-rebinding-forbidden')
    require(sha(args.root / 'out/w8b/occluded-render-01/source.json') == fixture['w8b_manifest_sha256'], 'w8b-manifest-seal-mismatch')
    outcomes = {}
    for case in CASES:
        try:
            outcomes[case] = run_case(args, case, fixture, av, fd)
        except AssertionError:
            outcomes[case] = 'RED'
    write_json(directory / 'summary.json', {'queue_comparison': '128 -> 1024', 'outcomes': outcomes,
        'all_public_green': all(value == 'PIXELS_AND_VCL_GREEN_EYE_PENDING' for value in outcomes.values()),
        'root_lower_image_eye': None, 'actual_argv': sys.argv,
        'runtime_environment': {key: os.environ.get(key) for key in (*NATIVE_ENV, 'OPENCV_FOR_THREADS_NUM')},
        'executable': sys.executable, 'fixtures_seal_sha256': sha(scratch(args.fixtures) / 'fixtures.json')})
    require(all(value != 'RED' for value in outcomes.values()), 'three-case-regression-red-see-summary')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        print(json.dumps({'code': str(error) if isinstance(error, AssertionError) else 'helper-failed',
                          'error_class': type(error).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
