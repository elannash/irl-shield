"""Paced, byte-preserving MPEG-TS replay into authenticated loopback SRT."""
from bisect import bisect_right
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import av

from relay.native_auth import SRT


def describe(path):
    path = Path(path)
    anchors, previous = [], {}
    counts = Counter()
    video_clock = elapsed = None
    with av.open(str(path)) as clip:
        for packet in clip.demux():
            if not packet.size or packet.dts is None or packet.time_base is None:
                continue
            counts[packet.stream.type + '_packets'] += 1
            counts['pts_ne_dts'] += packet.pts is not None and packet.pts != packet.dts
            stamp = float(packet.dts * packet.time_base)
            old = previous.get(packet.stream.index)
            counts['dts_regressions'] += old is not None and stamp < old
            previous[packet.stream.index] = stamp
            if packet.stream.type != 'video' or packet.pos is None or packet.pos < 0:
                continue
            if video_clock is None:
                elapsed = 0.
            else:
                step = stamp - video_clock
                if step < 0 or step > 2:
                    counts['pacing_discontinuities'] += 1
                    step = 1 / 30
                elapsed += step
            video_clock = stamp
            anchors.append((packet.pos, elapsed))
    if len(anchors) < 2 or counts['audio_packets'] == 0:
        raise ValueError('Replay requires timestamped video, audio and MPEG-TS byte positions')
    # Byte positions describe source order; pacing corrections never touch bytes.
    if any(b[0] < a[0] for a, b in zip(anchors, anchors[1:])):
        raise ValueError('MPEG-TS byte positions regress')
    data = path.read_bytes()
    if len(data) % 188 or data[0] != 0x47:
        raise ValueError('Replay requires raw MPEG-TS')
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(data).hexdigest(),
            'bytes': len(data), 'duration': anchors[-1][1] + 1 / 30,
            'packet_diagnostics': dict(counts)}, anchors


def publish(url, path, output, generation, stopped):
    """Spawn-pipe URL only. Neither upstream exception text nor URL is retained."""
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    av.logging.set_level(None)
    srt = None
    result = {'generation': generation, 'status': 'failed', 'messages': 0, 'loops': 0}
    phase = 'fixture-open'
    try:
        source, anchors = describe(path)
        data = Path(path).read_bytes()
        positions = [pos for pos, _ in anchors]
        result['source'] = source
        phase = 'srt-open'
        srt = SRT()
        result['libsrt'] = srt.receipt
        failed_since = None
        result['reconnects'] = 0
        while not stopped.is_set():
            try:
                with srt.connection(url) as fd:
                    phase = 'srt-send'
                    while not stopped.is_set():
                        start = time.monotonic()
                        for offset in range(0, len(data), 1316):
                            index = max(0, bisect_right(positions, offset) - 1)
                            if stopped.wait(max(0, start + anchors[index][1] - time.monotonic())):
                                break
                            srt.send(fd, data[offset:offset + 1316])
                            result['messages'] += 1
                        if stopped.is_set():
                            break
                        result['loops'] += 1
                        failed_since = None
                        stopped.wait(max(0, start + source['duration'] - time.monotonic()))
            except (ConnectionError, RuntimeError) as error:
                # A killed UDP/SRT publisher can retain camera ownership until
                # peer timeout. Retry the caller, never relax publisher ACLs.
                result['reconnects'] += 1
                result['last_connection_error'] = type(error).__name__
                failed_since = time.monotonic() if failed_since is None else failed_since
                if time.monotonic() - failed_since > 60:
                    raise RuntimeError('srt-replay-reconnect-limit') from None
                phase = 'srt-open'
                stopped.wait(.2)
        result['status'] = 'stopped'
    except Exception as error:
        result['failure'] = {'phase': phase, 'error_class': type(error).__name__}
    finally:
        if srt is not None:
            try:
                srt.close()
            except Exception:
                result['status'] = 'cleanup-failed'
        Path(output).write_text(json.dumps(result, indent=2) + '\n')
