"""Loopback-only verified-forwarder publication proof; synthetic CC0 media/certs.

Exit0: verified route and rejection controls hold. Exit1: an unverified peer
received a publication or plaintext/non-TLS bytes. Exit2: fixture/verification attribution unavailable.
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
from relay.mediamtx import verified_binary
from relay.stream import Egress, EgressError
from relay.tls_forwarder import TLSForwarder
from shield.types import Coverage, PresentedFrame
from tls_fixture import certificates
from wire_fixture import RawPeer


class FixtureError(RuntimeError):
    pass


def require_verification_rejection(row, server):
    if server.poll() is not None or row['publication_witness']:
        raise FixtureError('Rejection lacks a healthy unpublished peer')
    if (row['tls']['last_error'] != 'tls-verification-failed'
            or row['tls']['failures'] < 1 or not row['egress_error']):
        raise FixtureError('Rejection is not a TLS verification failure')
    wire = row['wire']
    if not wire['connections'] or not wire['bytes_received'] or wire['capture_errors']:
        raise FixtureError('Raw TCP rejection capture unavailable')
    return wire['canary_absent'] and wire['client_hello_and_controls_only']


def wait_witness(log, name, server):
    deadline = time.monotonic() + 4
    text = "is publishing to path 'app/" + name + "'"
    while text not in log.read_text():
        if server.poll() is not None or time.monotonic() >= deadline:
            raise FixtureError('Trusted publication control unavailable')
        time.sleep(.01)


@contextmanager
def server(binary, root, evidence):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    listener.close()
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
    log = evidence / 'mediamtx.log'
    with log.open('w') as output:
        process = subprocess.Popen([str(binary), str(config)], cwd=root,
                                   stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 4
            while 'started with listener on' not in log.read_text():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise FixtureError('TLS fixture listener unavailable')
                time.sleep(.01)
            yield process, port, log
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            (evidence / 'process.json').write_text(json.dumps({'pid': process.pid, 'exit': process.returncode}) + '\n')


def publish(port, name):
    output = None
    row = {'case': name, 'egress_error': None, 'refused': False, 'writes': 0}
    try:
        output = Egress(('rtmp://127.0.0.1:' + str(port) + '/app/' + name + '?bandwidthtest=true',),
                        None, width=64, height=32, encoder='libx264')
        for index in range(61):
            now = time.monotonic()
            frame = PresentedFrame(index, index / 30, np.zeros((32, 64, 3), np.uint8),
                np.full((32, 64), 255, np.uint8), [], Coverage(0, 0, True, 'synthetic'),
                'HOLD', now, now, False, True)
            accepted = output.write(frame, np.zeros(1600, np.int16))
            row['writes'] += 1
            if accepted is False:
                row.update(refused=True, egress_error=output.error_code)
                break
    except EgressError as error:
        row.update(refused=True, egress_error=error.code)
    finally:
        if output:
            try:
                output.close()
            except EgressError as error:
                row['cleanup_error'] = error.code
    return row


def audit(binary, evidence):
    report = {'scope': 'real Egress/PyAV/MediaMTX through verified loopback forwarder; no Twitch', 'rows': []}
    try:
        with tempfile.TemporaryDirectory(prefix='irl-shield-forwarder-') as temporary:
            root = certificates(Path(temporary))
            with server(binary, root, evidence) as (peer, port, log):
                resolve = socket.getaddrinfo
                def local_resolver(host, *args, **kwargs):
                    if host not in ('127.0.0.1', 'mismatch.invalid'):
                        raise FixtureError('Nonlocal fixture DNS refused')
                    return resolve('127.0.0.1', *args, **kwargs)
                with patch('socket.getaddrinfo', side_effect=local_resolver):
                    for name, hostname, authority in (
                            ('trusted-before', '127.0.0.1', 'peer'),
                            ('unrelated-ca', '127.0.0.1', 'other'),
                            ('mismatched-hostname', 'mismatch.invalid', 'peer'),
                            ('trusted-after', '127.0.0.1', 'peer')):
                        with RawPeer(port) as wire, TLSForwarder(hostname, wire.port, cafile=root / (authority + '.crt')) as forwarder:
                            row = publish(forwarder.port, name)
                            if not row['refused']:
                                wait_witness(log, name, peer)
                            row['tls'] = forwarder.stats
                        row['wire'] = wire.rejection(name.encode('ascii'))
                        row['publication_witness'] = "is publishing to path 'app/" + name + "'" in log.read_text()
                        row['server_alive'] = peer.poll() is None
                        report['rows'].append(row)
                        if not row['server_alive']:
                            raise FixtureError('Peer exited during publication controls')
                        if name.startswith('trusted'):
                            if row['refused'] or not row['publication_witness'] or row.get('cleanup_error'):
                                raise FixtureError('Trusted publication control failed')
                # Complete the post-negative trusted control even if a mutant
                # publishes; a dead or broken fixture must never earn a pass.
                unsafe_wire = []
                for row in report['rows'][1:3]:
                    if not row['publication_witness']:
                        unsafe_wire.append(not require_verification_rejection(row, peer))
                report['unsafe_rejection_wire'] = any(unsafe_wire)
                report['unverified_publication'] = any(row['publication_witness'] for row in report['rows'][1:3])
                return 1 if report['unverified_publication'] or report['unsafe_rejection_wire'] else 0
    except Exception as error:
        report['fixture_error'] = type(error).__name__
        report['fixture_reason'] = str(error) if isinstance(error, FixtureError) else 'Fixture failed; upstream text suppressed'
        return 2
    finally:
        (evidence / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    return audit(verified_binary(), args.out.resolve())


if __name__ == '__main__':
    raise SystemExit(main())
