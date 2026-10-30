"""Queue-only Linux RTMP/CUDA/NVENC evidence; all generated media is synthetic CC0.

Run as a foreground module with inherited canonical queue EX lease. No Twitch
connection, quality grading, held-out asset, native CLI or long-soak rerun.
"""
import argparse
import asyncio
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import threading
import time

import av
import cv2
import numpy as np
from aiohttp import ClientSession

from relay.fixture import decorate, tone
from relay.mediamtx import MediaMTX, verified_binary
from relay.runtime import make_engine, run
from relay.seal import seal
from relay.security import Credentials, RelayAddress
from relay.soak import Capture, analyze_capture, require_queue_lease
from shield.app.session import TwitchControls, login
from shield.twitch.http import TwitchHTTP
from mock_twitch import MockTwitch, until


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def sender(url, stopped, directory, generation):
    av.logging.set_level(None)
    cv2.setNumThreads(1)
    rows = []
    try:
        with av.open(url, 'w', format='flv', options={'flvflags': 'no_duration_filesize', 'flush_packets': '1'}) as output:
            video = output.add_stream('libx264', rate=30)
            video.width, video.height, video.pix_fmt = 1280, 720, 'yuv420p'
            video.codec_context.thread_count = 2
            video.codec_context.max_b_frames, video.codec_context.gop_size = 0, 30
            video.time_base = video.codec_context.time_base = Fraction(1, 30)
            video.options = {'preset': 'ultrafast', 'tune': 'zerolatency'}
            audio = output.add_stream('aac', rate=48000)
            audio.layout = 'mono'
            audio.codec_context.thread_count = 2
            audio.time_base = audio.codec_context.time_base = Fraction(1, 48000)
            origin = time.monotonic()
            index = 0
            while not stopped.is_set():
                if stopped.wait(max(0, origin + index / 30 - time.monotonic())):
                    break
                y, x = np.indices((720, 1280))
                pixels = np.stack(((x + index * 2) % 180 + 30, (y + index) % 180 + 30,
                                   (x // 7 + y // 7) % 180 + 30), axis=2).astype(np.uint8)
                epoch_ms = time.time_ns() // 1_000_000
                labels = decorate(pixels, index, epoch_ms)
                frame = av.VideoFrame.from_ndarray(pixels, format='bgr24')
                frame.pts, frame.time_base = index, Fraction(1, 30)
                sound = av.AudioFrame.from_ndarray(tone(index).reshape(1, -1), format='s16', layout='mono')
                sound.sample_rate, sound.pts, sound.time_base = 48000, index * 1600, Fraction(1, 48000)
                for stream, value in ((video, frame), (audio, sound)):
                    for packet in stream.encode(value):
                        output.mux(packet)
                rows.append({'index': index, 'epoch_ms': epoch_ms, 'generation': generation,
                             'labels': labels, 'flash': index % 30 < 3})
                index += 1
            for stream in (video, audio):
                for packet in stream.encode():
                    output.mux(packet)
        write(Path(directory) / f'sender-{generation}.json', {'status': 'closed', 'rows': rows})
    except Exception as error:
        write(Path(directory) / f'sender-{generation}.json', {'status': 'failed', 'error_class': type(error).__name__})
        raise SystemExit(2) from None


def stop_sender(process, stopped):
    stopped.set()
    process.join(5)
    if process.is_alive():
        process.terminate()
        process.join(3)
    if process.is_alive():
        process.kill()
        process.join(2)
    code = process.exitcode
    if process.is_alive():
        raise RuntimeError('Synthetic sender survived cleanup')
    process.close()
    return code


def frames(directory):
    path = directory / 'relay/frames.jsonl'
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    return [json.loads(line) for line in lines if line.endswith('}')]


def label_edges(pixels):
    # The common interior of both generator label boxes excludes the mask edge.
    boxes = [decorate(np.zeros_like(pixels), index, 0)[0]['bbox'] for index in (0, 150)]
    x0, y0 = max(b[0] for b in boxes) + 2, max(b[1] for b in boxes) + 2
    x1, y1 = min(b[2] for b in boxes) - 2, min(b[3] for b in boxes) - 2
    return int((cv2.Canny(pixels[y0:y1, x0:x1], 80, 180) > 0).sum())


def decode(directory, actions, manifest, archive):
    rows = []
    with av.open(str(directory / 'network.mkv')) as clip:
        for stream in clip.streams:
            stream.codec_context.thread_count = 2
        for frame in clip.decode(video=0):
            pixels = frame.to_ndarray(format='bgr24')
            rows.append({'pts': float(frame.pts * frame.time_base),
                         'black': bool(pixels.max() < 12), 'spatial': bool(pixels.std() > 3),
                         'label_edges': label_edges(pixels),
                         'pixels_sha256': hashlib.sha256(pixels.tobytes()).hexdigest()})
    if not rows:
        raise RuntimeError('No sink pixels decoded')
    offset = len(archive) - len(rows)
    matched = offset >= 0 and [r['pixels_sha256'] for r in rows] == [r['pixels_sha256'] for r in archive[offset:]]
    if not matched:
        raise RuntimeError('Network pixels do not match encoded archive suffix')
    for i, row in enumerate(rows):
        row['engine_index'] = manifest[i + offset]['index']
    archive_by_index = {f['index']: picture for f, picture in zip(manifest, archive, strict=True)}
    first, last = manifest[0]['encoded_at_monotonic'], manifest[-1]['encoded_at_monotonic']
    holds = []
    for i, action in enumerate(actions):
        if not action['active']:
            continue
        at = action.get('received_at', action['at'])
        release = next((a.get('received_at', a['at']) for a in actions[i + 1:]
                        if a['source'] == action['source'] and not a['active']), None)
        entry = {'source': action['source'], 'receipt_at': at, 'release_at': release}
        if at < first:
            active_at_first = release is None or release > first
            entry.update(phase='startup', active_at_first_emit=active_at_first,
                         pass_=not active_at_first or archive[0]['black'])
        elif at > last:
            entry.update(phase='after-output-shutdown', pass_=True)
        else:
            emitted = [f for f in manifest if f['encoded_at_monotonic'] >= at
                       and (release is None or f['encoded_at_monotonic'] < release)]
            live = [f['index'] for f in emitted if f['state'] == 'LIVE']
            black = next((f for f in emitted if archive_by_index[f['index']]['black']), None)
            delay = black['encoded_at_monotonic'] - at if black else None
            entry.update(phase='streaming', live_encoded_during_hold=live,
                         first_slate_index=black['index'] if black else None,
                         encoded_slate_delay_seconds=delay,
                         pass_=not live and delay is not None and delay <= 1 / 30)
        holds.append(entry)
    gaps = np.diff([r['pts'] for r in rows])
    write(directory / 'pixel-evidence.json', {'frames': rows, 'holds': holds,
          'archive_suffix_offset': offset, 'exact_pixel_suffix_match': matched})
    return {'decoded_frames': len(rows), 'spatial_frames': sum(r['spatial'] for r in rows),
            'black_frames': sum(r['black'] for r in rows), 'holds': holds,
            'max_label_edges': max(r['label_edges'] for r in rows),
            'label_edge_guard': all(r['label_edges'] < 60 for r in rows),
            'max_pts_gap_seconds': float(gaps.max()) if len(gaps) else None,
            'archive_suffix_offset': offset, 'exact_pixel_suffix_match': matched,
            'hold_latency_scope': 'control receipt to encoder completion + independently decoded pixel suffix',
            'no_all_slate_pass': any(r['spatial'] for r in rows)}


async def exercise(args, receipt):
    ctx = mp.get_context('spawn')
    stopped = threading.Event()
    captures, senders, cleanup = [], [], []
    controls = None
    engine = None
    work = None
    actions = []
    addresses = [RelayAddress('127.0.0.1', 19450, 18990, 18654),
                 RelayAddress('127.0.0.1', 19451, 18991, 18655)]
    credentials = [(Credentials.generate(), Credentials.generate()) for _ in addresses]
    with ExitStack() as stack:
        for address, (phone, internal) in zip(addresses, credentials):
            server = stack.enter_context(MediaMTX(address, phone, internal,
                binary=verified_binary(args.mediamtx_dir)))
            receipt.setdefault('owned_servers', []).append({'pid': server.process.pid,
                'host': address.host, 'rtmp_port': address.rtmp_port, 'rtsp_port': address.rtsp_port,
                'srt_port': address.srt_port})
        try:
            async with MockTwitch() as mock, ClientSession() as network:
                receipt['mock_origin'] = mock.origin
                http = TwitchHTTP(network, mock_origin=mock.origin)
                user = await login(http, 'synthetic-client', '1', asyncio.Event(), present=lambda _: None)
                controls = TwitchControls(user, http, stopped, mock_origin=mock.origin)
                await controls.prepare()
                engine = await asyncio.to_thread(make_engine, args.model_cache, 'cuda', ((24, 28),))
                control_box = []
                def register(control):
                    control_box.append(control)
                    original = control.hold
                    def observed(active, source='local', reason='manual', now=None):
                        received = time.monotonic()
                        value = original(active, source, reason, now)
                        actions.append({'at': time.monotonic(), 'received_at': received,
                                        'active': bool(active), 'source': source, 'reason': reason})
                        return value
                    control.hold = observed
                    controls.register(control)
                work = asyncio.create_task(asyncio.to_thread(run, engine, addresses[0], *credentials[0],
                    args.out / 'relay', stopped, 33, control_ready=register,
                    local_sink=addresses[1].rtmp('shielded', credentials[1][1])))
                for name, address in zip(('obs', 'sink'), addresses):
                    captures.append(Capture(address.rtsp('shielded'), args.out / name))
                def start_sender(generation):
                    stop = ctx.Event()
                    process = ctx.Process(target=sender, args=(addresses[0].rtmp('camera', credentials[0][0]),
                        stop, str(args.out), generation), name='integration-synthetic-sender')
                    process.start()
                    senders.append((process, stop))
                start_sender(1)
                await until(lambda: len(frames(args.out)) >= 150 or work.done(), 30)
                if work.done():
                    await work
                    raise RuntimeError('Relay ended before synthetic controls')
                await until(lambda: controls.events.phase == 'ready')
                await mock.send()
                await until(lambda: controls.events.remembered >= 1)
                await asyncio.sleep(1)
                await mock.send('!shield resume', actor='1')
                await until(lambda: controls.events.remembered >= 2)
                await asyncio.sleep(1)
                await mock.send(actor='1')
                await until(lambda: controls.events.remembered >= 3)
                await asyncio.sleep(1)
                await mock.send('!shield resume', actor='1')
                await until(lambda: controls.events.remembered >= 4)
                await mock.send(topic='channel.shield_mode.begin')
                await until(lambda: controls.events.remembered >= 5)
                control_box[0].hold(True)
                await mock.send(topic='channel.shield_mode.end')
                await until(lambda: controls.events.remembered >= 6)
                receipt['manual_survives_shield_end'] = engine.control.state == 'HOLD'
                process, stop = senders.pop()
                cleanup.append({'sender_exit': await asyncio.to_thread(stop_sender, process, stop)})
                await asyncio.sleep(2)
                start_sender(2)
                await asyncio.sleep(3)
                receipt['manual_survives_ingest_reconnect'] = engine.control.state == 'HOLD'
                control_box[0].hold(False)
                await work
                receipt['control_phase'] = controls.events.phase
        finally:
            stopped.set()
            for process, stop in senders:
                cleanup.append({'sender_exit': await asyncio.to_thread(stop_sender, process, stop)})
            if work:
                await work
            elif engine:
                engine.close()
            if controls:
                await controls.close()
            for capture in captures:
                await asyncio.to_thread(capture.close)
            receipt['cleanup'] = cleanup
            receipt['actions'] = actions
    receipt['all_owned_servers_exited'] = True
    manifest = frames(args.out)
    archive = []
    generations = sorted({row.get('egress_generation', 1) for row in manifest})
    for generation in generations:
        name = 'encoded.flv' if generation == 1 else f'encoded-g{generation:04d}.flv'
        decoded = []
        with av.open(str(args.out / 'relay' / name)) as movie:
            for frame in movie.decode(video=0):
                pixels = frame.to_ndarray(format='bgr24')
                decoded.append({'pixels_sha256': hashlib.sha256(pixels.tobytes()).hexdigest(),
                                'black': bool(pixels.max() < 12)})
        expected = sum(row.get('egress_generation', 1) == generation for row in manifest)
        if len(decoded) != expected:
            raise RuntimeError('Generation archive and acknowledged manifest counts disagree')
        archive.extend(decoded)
    receipt['pixels'] = {name: decode(args.out / name, actions, manifest, archive) for name in ('obs', 'sink')}
    source_rows = {}
    for path in args.out.glob('sender-*.json'):
        data = json.loads(path.read_text())
        for row in data.get('rows', []):
            source_rows[row['index']] = row
    receipt['av'] = {name: analyze_capture(args.out / name, source_rows) for name in ('obs', 'sink')}
    receipt['runtime'] = json.loads((args.out / 'relay/runtime.json').read_text())
    receipt['assertions_pass'] = (all(p['no_all_slate_pass'] and p['label_edge_guard']
        and p['holds'] and all(h['pass_'] for h in p['holds'])
        for p in receipt['pixels'].values()) and receipt['manual_survives_shield_end']
        and receipt['manual_survives_ingest_reconnect']
        and receipt['runtime']['session']['sessions'] >= 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--mediamtx-dir', type=Path, required=True)
    parser.add_argument('--model-cache', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    lease = require_queue_lease()
    receipt = {'status': 'failed', 'lease': lease,
        'forced': os.environ.get('IRL_SHIELD_PERF_QUEUE_FORCED') == '1',
        'cli_mock': 'NOT RUN BY DESIGN (local-only boundary); protocol receipts in merged PR2 54740e1',
        'privacy': 'natural-scene privacy unqualified; synthetic interior-edge guard only; no Q grading',
        'asset': 'Generated synthetic CC0 labels/pattern/timing tone; no source music/brands'}
    try:
        cv2.setNumThreads(1)
        av.logging.set_level(None)
        asyncio.run(exercise(args, receipt))
        receipt['status'] = 'functional-pass' if receipt['assertions_pass'] else 'assertion-failure'
    except Exception as error:
        receipt['error_class'] = type(error).__name__
        receipt['failure'] = 'Native integration failed; credentialed diagnostics suppressed'
    receipt['qualified'] = False
    write(args.out / 'receipt.json', receipt)
    digest = seal(args.out)
    print(json.dumps({'status': receipt['status'], 'qualified': False, 'seal_sha256': digest}))
    return 0 if receipt.get('assertions_pass') else 2


if __name__ == '__main__':
    raise SystemExit(main())
