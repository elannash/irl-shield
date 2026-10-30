"""Standalone Linux security probe, not a unittest or a passing gate.

Run directly as documented in docs/PR5-TLS-FOLLOWUP.md. Exit 1 means PyAV
published to a peer rejected by native verification controls. Exit 2 means
the fixture/controls failed; neither result establishes safe relay egress.
Synthetic certificates and silent black frames are CC0. No external network.
"""
import argparse
import ctypes as c
from fractions import Fraction
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time

import av


def native_open(url, options):
    # Load the wheel's actual libraries, never the host's FFmpeg installation.
    libraries = Path(av.__file__).parent.parent / 'av.libs'
    formats = c.CDLL(str(next(libraries.glob('libavformat-*.so*'))))
    utils = c.CDLL(str(next(libraries.glob('libavutil-*.so*'))))
    formats.avio_open2.argtypes = [c.POINTER(c.c_void_p), c.c_char_p, c.c_int,
                                  c.c_void_p, c.POINTER(c.c_void_p)]
    formats.avio_open2.restype = c.c_int
    formats.avio_closep.argtypes = [c.POINTER(c.c_void_p)]
    formats.avio_closep.restype = c.c_int
    utils.av_dict_set.argtypes = [c.POINTER(c.c_void_p), c.c_char_p, c.c_char_p, c.c_int]
    utils.av_dict_set.restype = c.c_int
    utils.av_dict_free.argtypes = [c.POINTER(c.c_void_p)]
    io, dictionary = c.c_void_p(), c.c_void_p()
    try:
        for name, value in options.items():
            code = utils.av_dict_set(c.byref(dictionary), name.encode(), value.encode(), 0)
            if code < 0:
                raise RuntimeError('Native option dictionary allocation failed')
        return formats.avio_open2(c.byref(io), url.encode(), 2, None, c.byref(dictionary))
    finally:
        if io.value:
            formats.avio_closep(c.byref(io))
        utils.av_dict_free(c.byref(dictionary))


def publish(url, options, custom_io=False):
    calls = []

    def io_open(*args):
        calls.append(True)
        raise RuntimeError('Primary output unexpectedly reached custom I/O')

    kwargs = {'io_open': io_open} if custom_io else {}
    with av.open(url, 'w', format='flv', options=options, **kwargs) as output:
        stream = output.add_stream('libx264', rate=30)
        stream.width, stream.height, stream.pix_fmt = 64, 32, 'yuv420p'
        stream.codec_context.thread_count = 2
        stream.options = {'preset': 'ultrafast', 'tune': 'zerolatency'}
        output.start_encoding()
        frame = av.VideoFrame(64, 32, 'yuv420p')
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        frame.time_base = Fraction(1, 30)
        # MediaMTX needs a media interval to identify the track; a lone packet
        # can close before publication is witnessed. This is not paced/timed.
        for index in range(61):
            frame.pts = index
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    return len(calls)


def wait_for(log, text, server):
    deadline = time.monotonic() + 3
    while text not in log.read_text():
        if server.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError('Missing MediaMTX witness: ' + text)
        time.sleep(.01)


def audit(binary, evidence, controls_only):
    with tempfile.TemporaryDirectory(prefix='certificates-', dir=evidence) as directory:
        root = Path(directory)
        for name in ('peer', 'other'):
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-days', '1', '-subj', '/CN=localhost', '-addext',
                            'subjectAltName=DNS:localhost', '-keyout', str(root / (name + '.key')),
                            '-out', str(root / (name + '.crt'))], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        config = root / 'mediamtx.yml'
        config.write_text(f'''logLevel: info
rtsp: false
rtmp: true
rtmpEncryption: strict
rtmpsAddress: 127.0.0.1:{port}
rtmpServerKey: {root / 'peer.key'}
rtmpServerCert: {root / 'peer.crt'}
hls: false
webrtc: false
srt: false
moq: false
api: false
metrics: false
pprof: false
playback: false
paths:
  all_others:
''')
        logpath = evidence / 'mediamtx.log'
        with logpath.open('w') as log:
            server = subprocess.Popen([str(binary), str(config)], cwd=root,
                                      stdout=log, stderr=subprocess.STDOUT)
            report = {'av': av.__version__, 'libraries': av.library_versions, 'rows': []}
            try:
                wait_for(logpath, 'started with listener on', server)
                good = {'tls_verify': '1', 'ca_file': str(root / 'peer.crt'),
                        'verifyhost': 'localhost', 'rw_timeout': '1000000'}
                controls = [('native-trusted', {}, True),
                            ('native-untrusted', {'ca_file': str(root / 'other.crt')}, False),
                            ('native-mismatched', {'verifyhost': 'wrong.invalid'}, False)]
                for name, override, expected in controls:
                    url = f'rtmps://127.0.0.1:{port}/audit/{name}?bandwidthtest=true'
                    code = native_open(url, good | override)
                    report['rows'].append({'case': name, 'accepted': code >= 0, 'code': code})
                    if (code >= 0) != expected:
                        raise RuntimeError('Native verification control failed: ' + name)
                if controls_only:
                    report['scope'] = 'backend controls only; relay peer verification untested'
                    return 0
                cases = [('pyav-default', {}, '', False),
                         ('pyav-trusted-options', good, '', False),
                         ('pyav-untrusted-options', good | {'ca_file': str(root / 'other.crt')}, '', False),
                         ('pyav-mismatched-options', good | {'verifyhost': 'wrong.invalid'}, '', False),
                         ('pyav-query', {}, '&verify=1', False),
                         ('pyav-io-open', good | {'ca_file': str(root / 'other.crt')}, '', True)]
                for name, options, query, custom in cases:
                    url = f'rtmps://127.0.0.1:{port}/audit/{name}?bandwidthtest=true{query}'
                    row = {'case': name, 'accepted': False, 'publication_witness': False}
                    try:
                        row['custom_io_calls'] = publish(
                            url, {'flvflags': 'no_duration_filesize'} | options, custom)
                        row['accepted'] = True
                    except av.FFmpegError as error:
                        row['error'] = type(error).__name__
                    report['rows'].append(row)
                    if row['accepted']:
                        wait_for(logpath, f"is publishing to path 'audit/{name}'", server)
                        row['publication_witness'] = True
                if not all(row['accepted'] for row in report['rows'][3:5]):
                    raise RuntimeError('PyAV default/trusted publication control failed')
                report['unverified_publication'] = any(row['accepted'] for row in report['rows'][5:])
                return 1 if report['unverified_publication'] else 0
            finally:
                server.terminate()
                try:
                    server.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=3)
                report['owned_mediamtx_pid'] = server.pid
                report['owned_mediamtx_exit'] = server.returncode
                (evidence / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
                print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mediamtx', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--controls-only', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        return audit(args.mediamtx.resolve(), args.out.resolve(), args.controls_only)
    except Exception as error:
        print('FIXTURE ERROR:', type(error).__name__, str(error))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
