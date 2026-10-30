"""Real Linux ingest ACL probe; benchmark-only H.264 remux, no encoder or Twitch."""
import argparse
import ctypes
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import socket
import struct
import threading
import time
import traceback
from urllib.parse import parse_qs, urlsplit

import av

from relay.mediamtx import MediaMTX, linux_bound_sockets, verified_binary
from relay.security import Credentials, RelayAddress


class SRT:
    """Probe-only adapter for the system libsrt 1.5 C ABI (MPL-2.0).

    ABI reference: https://github.com/Haivision/srt/blob/v1.5.4/srtcore/srt.h
    No URLs or upstream errors leave this adapter; credentials stay in memory.
    """
    def __init__(self, library='/usr/lib/x86_64-linux-gnu/libsrt-gnutls.so.1.5'):
        self.library = Path(library).resolve()
        self.lib = ctypes.CDLL(str(self.library))
        signatures = {
            'srt_startup': ([], ctypes.c_int),
            'srt_cleanup': ([], ctypes.c_int),
            'srt_create_socket': ([], ctypes.c_int),
            'srt_close': ([ctypes.c_int], ctypes.c_int),
            'srt_setloglevel': ([ctypes.c_int], None),
            'srt_getversion': ([], ctypes.c_uint32),
            'srt_setsockflag': ([ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            'srt_bind': ([ctypes.c_int, ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            'srt_connect': ([ctypes.c_int, ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            'srt_sendmsg': ([ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int),
            'srt_recvmsg': ([ctypes.c_int, ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result
        self.lib.srt_setloglevel(-1)
        if self.lib.srt_startup() != 0:
            raise RuntimeError('SRT initialization failed')

    @property
    def receipt(self):
        version = self.lib.srt_getversion()
        return {'version': '.'.join(str((version >> shift) & 255) for shift in (16, 8, 0)),
                'library': str(self.library), 'license': 'MPL-2.0',
                'sha256': hashlib.sha256(self.library.read_bytes()).hexdigest()}

    def close(self):
        if self.lib.srt_cleanup() != 0:
            raise RuntimeError('SRT cleanup failed')

    @contextmanager
    def connection(self, url):
        parsed = urlsplit(url)
        streamid = parse_qs(parsed.query)['streamid'][0].encode()
        fd = self.lib.srt_create_socket()
        if fd < 0:
            raise RuntimeError('SRT socket creation failed')
        try:
            # SRTO_CONNTIMEO=36, SRTO_SNDTIMEO=13, SRTO_RCVTIMEO=14;
            # SRTO_STREAMID=46 in the versioned public C ABI.
            for option in (36, 13, 14):
                timeout = ctypes.c_int(1500)
                if self.lib.srt_setsockflag(fd, option, ctypes.byref(timeout), ctypes.sizeof(timeout)) != 0:
                    raise RuntimeError('SRT timeout configuration failed')
            if self.lib.srt_setsockflag(fd, 46, streamid, len(streamid)) != 0:
                raise RuntimeError('SRT stream configuration failed')
            def sockaddr(port):
                return struct.pack('=H', socket.AF_INET) + struct.pack('!H', port) + socket.inet_aton(parsed.hostname) + bytes(8)
            # Restrict even the probe's ephemeral UDP client to the assigned IP.
            local, remote = sockaddr(0), sockaddr(parsed.port)
            if self.lib.srt_bind(fd, local, len(local)) != 0:
                raise RuntimeError('SRT client bind failed')
            if self.lib.srt_connect(fd, remote, len(remote)) != 0:
                raise ConnectionError('SRT connection rejected')
            yield fd
        finally:
            if self.lib.srt_close(fd) != 0:
                raise RuntimeError('SRT socket cleanup failed')

    def accepts(self, url):
        try:
            with self.connection(url):
                return True
        except ConnectionError:
            return False

    def send(self, fd, data):
        for offset in range(0, len(data), 1316):
            chunk = data[offset:offset + 1316]
            if self.lib.srt_sendmsg(fd, chunk, len(chunk), -1, 0) != len(chunk):
                raise RuntimeError('SRT packet transfer failed')
        return len(data)

    def receive(self, fd):
        buffer = ctypes.create_string_buffer(2048)
        length = self.lib.srt_recvmsg(fd, buffer, len(buffer))
        if length <= 0:
            raise RuntimeError('SRT receive failed')
        return buffer.raw[:length]


class _SRTWriter:
    def __init__(self, srt, fd):
        self.srt, self.fd = srt, fd

    def write(self, data):
        return self.srt.send(self.fd, data)

    def writable(self):
        return True


def _remux(sink, fixture, stopped, ready, counts):
    with av.open(str(fixture)) as source:
        video = source.streams.video[0]
        target = sink.add_stream_from_template(video)
        for packet in source.demux(video):
            if stopped.is_set():
                break
            if packet.dts is None:
                continue
            packet.stream = target
            sink.mux(packet)
            counts['sent_packets'] += 1
            ready.set()
            # Give readers time to join without buffering or re-encoding frames.
            if stopped.wait(1 / 60):
                break


@contextmanager
def publishing(protocol, url, fixture, srt):
    stopped, ready = threading.Event(), threading.Event()
    counts = {'sent_packets': 0, 'publisher_failed': False}
    def worker():
        try:
            if protocol == 'rtmp':
                with av.open(url, 'w', format='flv', timeout=2) as sink:
                    _remux(sink, fixture, stopped, ready, counts)
            else:
                with srt.connection(url) as fd:
                    with av.open(_SRTWriter(srt, fd), 'w', format='mpegts', buffer_size=1316) as sink:
                        _remux(sink, fixture, stopped, ready, counts)
        except Exception:
            counts['publisher_failed'] = True
            ready.set()
    thread = threading.Thread(target=worker, name='ingest-acl-publisher')
    thread.start()
    try:
        if not ready.wait(3) or counts['publisher_failed']:
            raise RuntimeError('Authenticated probe publisher failed')
        yield counts
    finally:
        stopped.set()
        thread.join(4)
        if thread.is_alive():
            raise RuntimeError('Probe publisher did not stop')


def rtmp_publish(url, fixture):
    """Unauthorized attempts must fail on remux/flush, never on a mock."""
    try:
        with av.open(str(fixture)) as source, av.open(url, 'w', format='flv', timeout=2) as sink:
            video = source.streams.video[0]
            target = sink.add_stream_from_template(video)
            count = 0
            for packet in source.demux(video):
                if packet.dts is not None:
                    packet.stream = target
                    sink.mux(packet)
                    count += 1
                    if count == 30:
                        return True
    except Exception:
        return False
    return False


def rtmp_read(url):
    try:
        with av.open(url, timeout=2) as source:
            count = 0
            for packet in source.demux(video=0):
                if packet.dts is not None and packet.size:
                    count += 1
                    if count == 3:
                        return count
    except Exception:
        return 0
    return 0


def srt_read(srt, url):
    # A successful publish handshake precedes MediaMTX's MPEG-TS track parsing.
    # Wait for the real read connection, rather than treating the first packet
    # handed to the muxer as proof that a readable path already exists.
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        try:
            with srt.connection(url) as fd:
                packets = [srt.receive(fd) for _ in range(3)]
                return sum(bool(data) and len(data) % 188 == 0 and data[0] == 0x47 for data in packets)
        except ConnectionError:
            time.sleep(.02)
        except RuntimeError:
            return 0
    return 0


def occupied_ports(address, binary):
    results = {}
    for protocol, kind, port in (('rtmp', socket.SOCK_STREAM, address.rtmp_port),
                                 ('srt', socket.SOCK_DGRAM, address.srt_port)):
        with socket.socket(socket.AF_INET, kind) as incumbent:
            if kind == socket.SOCK_STREAM:
                incumbent.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            incumbent.bind((address.host, port))
            if kind == socket.SOCK_STREAM:
                incumbent.listen()
            server = MediaMTX(address, Credentials.generate(), Credentials.generate(), binary)
            rejected = False
            try:
                with server:
                    pass
            except RuntimeError:
                rejected = True
            results[protocol + '_occupied_rejected'] = rejected
            results[protocol + '_failed_child_exited'] = server.process is not None and server.process.poll() is not None
    return results


def probe(fixture, address, binary=None):
    av.logging.set_level(-8)
    binary = binary or verified_binary()
    results = {'startup': occupied_ports(address, binary)}
    phone, internal = Credentials.generate(), Credentials.generate()
    srt = SRT()
    try:
        results['srt_library'] = srt.receipt
        with MediaMTX(address, phone, internal, binary) as server:
            results['server_pid'] = server.process.pid
            process_root = Path(f'/proc/{server.process.pid}')
            process_metadata = (process_root / 'environ').read_bytes() + (process_root / 'cmdline').read_bytes()
            results['credentials_absent_from_env_and_argv'] = all(
                value.encode() not in process_metadata
                for credentials in (phone, internal) for value in (credentials.user, credentials.password))
            results['diagnostics_discarded'] = all(
                (process_root / 'fd' / str(fd)).readlink() == Path('/dev/null') for fd in (1, 2))
            results['sockets'] = sockets = linux_bound_sockets(server.process.pid)
            results['bindings_restricted'] = {(x['protocol'], x['host'], x['port']) for x in sockets} == {
                ('tcp', address.host, address.rtmp_port), ('udp', address.host, address.srt_port)}
            bad = Credentials(phone.user, 'synthetic-incorrect-password')
            for protocol in ('rtmp', 'srt'):
                def publish_url(path, creds=None):
                    return address.rtmp(path, creds) if protocol == 'rtmp' else address.srt('publish', path, creds)
                def read_url(path, creds=None):
                    return address.rtmp(path, creds) if protocol == 'rtmp' else address.srt('read', path, creds)
                def accepts(url):
                    return rtmp_publish(url, fixture) if protocol == 'rtmp' else srt.accepts(url)
                checks = results[protocol] = {
                    'anonymous_publish_rejected': not accepts(publish_url('camera')),
                    'bad_credentials_rejected': not accepts(publish_url('camera', bad)),
                    'phone_cannot_publish_egress': not accepts(publish_url('shielded', phone)),
                    'internal_cannot_publish_camera': not accepts(publish_url('camera', internal)),
                    'unknown_path_rejected': not accepts(publish_url('camera', phone).replace('/camera', '/unconfigured') if protocol == 'rtmp'
                                                         else publish_url('camera', phone).replace('publish%3Acamera', 'publish%3Aunconfigured')),
                }
                for path, publisher, reader in (('camera', phone, internal), ('shielded', internal, None)):
                    with publishing(protocol, publish_url(path, publisher), fixture, srt) as counts:
                        if protocol == 'rtmp':
                            received = rtmp_read(read_url(path, reader))
                        else:
                            received = srt_read(srt, read_url(path, reader))
                        checks[path + '_received_packets'] = received
                        checks[path + '_media_received'] = received >= 3
                        if path == 'camera':
                            for label, creds in (('anonymous', None), ('phone', phone), ('bad', bad)):
                                accepted = bool(rtmp_read(read_url(path, creds))) if protocol == 'rtmp' else srt.accepts(read_url(path, creds))
                                checks[label + '_camera_read_rejected'] = not accepted
                        checks[path + '_sent_packets'] = counts['sent_packets']
                    checks[path + '_publisher_clean'] = not counts['publisher_failed']
        results['server_exit'] = server.process.returncode
        results['server_stopped'] = server.process.poll() is not None
    finally:
        srt.close()
    return results


def passed(result):
    return (result['bindings_restricted'] and result['server_stopped'] and result['server_exit'] == 0
            and result['credentials_absent_from_env_and_argv'] and result['diagnostics_discarded']
            and all(result['startup'].values())
            and all(value for protocol in ('rtmp', 'srt') for value in result[protocol].values() if isinstance(value, bool)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--rtmp-port', type=int, default=19450)
    parser.add_argument('--srt-port', type=int, default=18950)
    parser.add_argument('--tool-directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        binary = verified_binary(args.tool_directory) if args.tool_directory else None
        result = probe(args.fixture, RelayAddress(args.host, args.rtmp_port, args.srt_port), binary)
    except Exception as error:
        # Frame locations identify the failed step without serializing upstream
        # exception messages, URL-bearing locals, or credentialed arguments.
        failure = {'status': 'failed', 'error_type': type(error).__name__,
                   'frames': [{'file': Path(frame.filename).name, 'line': frame.lineno,
                               'function': frame.name}
                              for frame in traceback.extract_tb(error.__traceback__)]}
        args.output.write_text(json.dumps(failure, indent=2) + '\n')
        print(json.dumps(failure))
        raise SystemExit('Relay ACL probe failed; upstream diagnostics suppressed') from None
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    if not passed(result):
        raise SystemExit('Relay socket ACL failed')


if __name__ == '__main__':
    main()
