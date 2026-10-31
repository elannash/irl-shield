"""Single-pass RTMP phone-input sender. Endpoint objects stay in process memory."""
from fractions import Fraction
import hashlib
import ipaddress
import json
import multiprocessing
from multiprocessing.reduction import DupFd
import os
from pathlib import Path
import resource
import time

from .lease import LEASE_ENV, inherited_exclusive
from .source import FPS, SECONDS, sha256


def endpoint(address, phone, *, local_only):
    host = ipaddress.IPv4Address(address.host)
    if local_only and str(host) != '127.0.0.1':
        raise ValueError('W8 local rehearsal requires exact loopback')
    if not (str(host) == '127.0.0.1' or host in ipaddress.IPv4Network('100.64.0.0/10')):
        raise ValueError('W8 input requires a private relay')
    return address.rtmp('camera', phone)


def source_manifest(path):
    path = Path(path).resolve()
    manifest = json.loads(path.read_text())
    video = path.parent / 'source.mp4'
    if (manifest['schema'] != 'irl-shield-w8-source-v1' or manifest['video'] != video.name
            or manifest['fps'] != FPS or manifest['seconds'] != SECONDS
            or len(manifest['frames']) != FPS * SECONDS or sha256(video) != manifest['video_sha256']):
        raise ValueError('W8 sender source seal mismatch')
    for index, frame in enumerate(manifest['frames']):
        if type(frame['source_index']) is not int or frame['source_index'] != index or Fraction(frame['pts']) != Fraction(index, FPS):
            raise ValueError('W8 source identity mismatch')
    return video, manifest


def _send(manifest_path, url, stopped, receipt):
    lease = os.fstat(inherited_exclusive())
    import av
    av.logging.set_level(None)
    video, manifest = source_manifest(manifest_path)
    with Path(receipt).open('x') as log, av.open(str(video)) as source:
        log.write(json.dumps({'kind': 'sender-start', 'source_manifest_sha256': sha256(manifest_path),
            'lease_device': lease.st_dev, 'lease_inode': lease.st_ino,
            'lease_mode': 'verified-FLOCK-WRITE', 'at_monotonic': time.monotonic()}) + '\n')
        incoming = source.streams.video[0]
        # Remux, rather than re-encode: preserves the source's H.264 access units.
        with av.open(url, 'w', format='flv', timeout=(2., 2.)) as output:
            outgoing = output.add_stream_from_template(incoming)
            started, count = time.monotonic(), 0
            for packet in source.demux(incoming):
                if packet.dts is None:
                    continue
                if packet.pts is None or packet.pts != packet.dts:
                    raise ValueError('W8 sender requires no B frames')
                pts = packet.pts * packet.time_base
                if count >= len(manifest['frames']) or pts != Fraction(count, FPS):
                    raise ValueError('W8 packet clock mismatch')
                if stopped.wait(max(0., started + float(pts) - time.monotonic())):
                    break
                emitted = time.monotonic()
                digest = hashlib.sha256(bytes(packet)).hexdigest()
                packet.stream = outgoing
                output.mux(packet)
                log.write(json.dumps({'source_index': count, 'source_pts': str(pts),
                    'source_decoded_pixels_sha256': manifest['frames'][count]['pixels_sha256'],
                    'avcc_packet_sha256': digest, 'mux_started_at_monotonic': emitted,
                    'mux_finished_at_monotonic': time.monotonic()}) + '\n')
                count += 1
            log.write(json.dumps({'kind': 'sender-end', 'packets': count,
                'complete': count == FPS * SECONDS, 'stopped': stopped.is_set(),
                'finished_at_monotonic': time.monotonic(),
                'evidence_scope': 'publisher only; not decoder arrival or native proof'}) + '\n')


def _worker(lease, manifest, url, stopped, receipt):
    fd = lease.detach()
    os.environ[LEASE_ENV] = str(fd)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        _send(manifest, url, stopped, receipt)
    except BaseException:
        # Native exception strings and tracebacks can contain the endpoint.
        raise SystemExit(2) from None
    finally:
        os.close(fd)


class Sender:
    """Root's phone-ready callback owns this context inside the relay lifetime."""
    def __init__(self, manifest, address, phone, receipt, *, local_only=True):
        fd = inherited_exclusive()
        url = endpoint(address, phone, local_only=local_only)
        self.receipt = Path(receipt)
        if self.receipt.exists():
            raise ValueError('Use a fresh W8 sender receipt')
        context = multiprocessing.get_context('spawn')
        self.stopped = context.Event()
        self._complete_checked = False
        self.process = context.Process(target=_worker,
            args=(DupFd(fd), str(manifest), url, self.stopped, str(receipt)), name='w8-phone-input')

    def __enter__(self):
        try:
            self.process.start()
        except BaseException:
            if self.process.pid is not None:
                self.__exit__(None, None, None)
            raise
        return self

    def check(self):
        if self.process.exitcode not in (None, 0):
            raise RuntimeError('W8 sender failed; private diagnostics suppressed')
        if self.process.exitcode == 0 and not self._complete_checked:
            rows = self.receipt.read_text().splitlines()
            terminal = json.loads(rows[-1]) if rows else {}
            if terminal.get('kind') != 'sender-end' or terminal.get('complete') is not True:
                raise RuntimeError('W8 sender ended before the complete single shot')
            self._complete_checked = True

    def __exit__(self, kind, value, traceback):
        self.stopped.set()
        self.process.join(6)
        forced = self.process.is_alive()
        if forced:
            self.process.terminate()
            self.process.join(3)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(3)
        if self.process.is_alive():
            raise RuntimeError('W8 owned sender survived cleanup')
        self.check()
        if forced:
            raise RuntimeError('W8 sender required forced cleanup')
