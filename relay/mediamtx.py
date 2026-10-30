"""Owned Linux MediaMTX process; credentialed config travels over stdin only."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time

from relay.security import mediamtx_environment

VERSION = 'v1.21.3'
ARCHIVE_SHA256 = '0a2ea7eba96023631efa1bea7804823a9145b043b6646a8a05798d4ac24ed635'
BINARY_SHA256 = 'bfa372a169751bbf6da2ebddcbcd2f7d3ab3dca3cc553022162eda36fe03e73d'
TOOL_DIR = Path(__file__).resolve().parents[1] / '.tmp/tools' / ('mediamtx-' + VERSION)


def verified_binary(directory=TOOL_DIR):
    path = Path(directory) / 'mediamtx'
    if hashlib.sha256(path.read_bytes()).hexdigest() != BINARY_SHA256:
        raise RuntimeError('MediaMTX binary verification failed')
    return path


class MediaMTX:
    def __init__(self, address, phone, internal, binary=None):
        self.address, self.phone, self.internal = address, phone, internal
        self.binary = binary or verified_binary()
        self.process = None

    def __enter__(self):
        if self.process is not None:
            raise RuntimeError('MediaMTX context cannot be reused')
        # Never inherit ambient MTX_* overrides or emit upstream diagnostics: they
        # can contain authenticated URL/query strings, including rejected clients.
        env = {k: v for k, v in os.environ.items() if not k.startswith('MTX_')}
        env.update(mediamtx_environment(self.address, self.phone, self.internal))
        users = json.loads(env.pop('MTX_AUTHINTERNALUSERS'))
        try:
            self.process = subprocess.Popen([str(self.binary), '/dev/stdin'], env=env,
                                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)
            self.process.stdin.write(json.dumps({'authInternalUsers': users, 'paths': {
                'camera': {'source': 'publisher', 'overridePublisher': False},
                'shielded': {'source': 'publisher', 'overridePublisher': False}},
                'pathDefaults': {'record': False}, 'dumpPackets': False}).encode())
            self.process.stdin.close()
            expected = {('tcp', self.address.host, self.address.rtmp_port),
                        ('udp', self.address.host, self.address.srt_port)}
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('MediaMTX startup failed (diagnostics suppressed)')
                sockets = {(row['protocol'], row['host'], row['port'])
                           for row in linux_bound_sockets(self.process.pid)}
                if sockets - expected:
                    raise RuntimeError('MediaMTX opened an unexpected listener')
                if sockets == expected and self.process.poll() is None:
                    return self
                time.sleep(.02)
            raise RuntimeError('MediaMTX startup timed out')
        except Exception:
            self.__exit__(None, None, None)
            raise RuntimeError('MediaMTX startup failed (diagnostics suppressed)') from None
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *error):
        if self.process is not None:
            if self.process.stdin is not None and not self.process.stdin.closed:
                try:
                    self.process.stdin.close()
                except OSError:
                    # A child rejecting config can close its pipe first. Still
                    # reap that same child before returning the startup error.
                    pass
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)


def linux_bound_sockets(pid):
    """Inspect only this child's socket inodes; no other session's endpoints."""
    import struct
    inodes = set()
    try:
        fds = list(Path(f'/proc/{pid}/fd').iterdir())
    except FileNotFoundError:
        return []
    for fd in fds:
        try:
            target = fd.readlink().as_posix()
        except FileNotFoundError:
            continue
        if target.startswith('socket:['):
            inodes.add(target[8:-1])
    rows = []
    for protocol in ('tcp', 'tcp6', 'udp', 'udp6'):
        try:
            lines = Path(f'/proc/{pid}/net/{protocol}').read_text().splitlines()[1:]
        except FileNotFoundError:
            return []
        for line in lines:
            fields = line.split()
            if fields[9] not in inodes:
                continue
            if protocol.startswith('tcp') and fields[3] != '0A':
                continue
            host, port = fields[1].split(':')
            if protocol.endswith('6'):
                raise RuntimeError('Unexpected IPv6 relay socket')
            host = socket.inet_ntoa(struct.pack('<I', int(host, 16)))
            rows.append({'protocol': protocol, 'host': host, 'port': int(port, 16)})
    return rows
