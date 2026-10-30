"""Original CC0 synthetic recovery fixtures; no music, logos or location text.

The parser is test-only: it locates a valid server chunk boundary for the run-68
Ping fault. It is deliberately never installed on the production stream path.
"""
from contextlib import ExitStack
import json
import multiprocessing
import os
from pathlib import Path
import select
import socket
import threading
import time
from urllib.parse import urlsplit, urlunsplit

import numpy as np

from relay.bridge import NoOpDetector
from relay.mediamtx import MediaMTX
from relay.security import Credentials, RelayAddress
from shield.engine import MaskingEngine
from shield.lanes import DetectorLane


class MessageGate:
    def __init__(self):
        self.handshake = 3073
        self.buffer = bytearray()
        self.pending = bytearray()
        self.streams = {}
        self.chunk_size = 128

    @property
    def at_boundary(self):
        return not (self.handshake or self.buffer or self.pending)

    def feed(self, data):
        ready = []
        if self.handshake:
            count = min(len(data), self.handshake)
            ready.append(data[:count])
            self.handshake -= count
            data = data[count:]
        self.buffer.extend(data)
        if len(self.buffer) + len(self.pending) > 262144:
            raise ValueError('rtmp-control-buffer-bound')
        while self.buffer:
            parsed = self._chunk()
            if parsed is None:
                break
            count, channel, state, payload = parsed
            self.pending.extend(self.buffer[:count])
            del self.buffer[:count]
            self.streams[channel] = state
            if len(self.streams) > 128:
                raise ValueError('rtmp-control-stream-bound')
            if state['kind'] == 1:
                state['body'] = state.get('body', b'') + payload
                if state['offset'] == 0:
                    if len(state['body']) != 4:
                        raise ValueError('rtmp-chunk-size-message')
                    self.chunk_size = int.from_bytes(state['body'], 'big') & 0x7fffffff
                    if not 1 <= self.chunk_size <= 65536:
                        raise ValueError('rtmp-chunk-size-bound')
            if not any(value['offset'] for value in self.streams.values()):
                ready.append(bytes(self.pending))
                self.pending.clear()
        return ready

    def _chunk(self):
        data = self.buffer
        kind, channel = data[0] >> 6, data[0] & 63
        cursor = 1
        if channel == 0:
            if len(data) < 2:
                return None
            channel = 64 + data[1]
            cursor = 2
        elif channel == 1:
            if len(data) < 3:
                return None
            channel = 64 + data[1] + 256 * data[2]
            cursor = 3
        old = self.streams.get(channel)
        length = (11, 7, 3, 0)[kind]
        if len(data) < cursor + length:
            return None
        if kind == 0:
            state = {'size': int.from_bytes(data[cursor+3:cursor+6], 'big'),
                     'kind': data[cursor+6], 'offset': 0}
        elif old is None:
            raise ValueError('rtmp-missing-stream-header')
        else:
            state = dict(old)
            if kind == 1:
                state.update(size=int.from_bytes(data[cursor+3:cursor+6], 'big'),
                             kind=data[cursor+6], offset=0, body=b'')
            elif not state['offset']:
                state['body'] = b''
        extended = (int.from_bytes(data[cursor:cursor+3], 'big') == 0xffffff
                    if kind != 3 else old['extended'])
        state['extended'] = extended
        cursor += length + (4 if extended else 0)
        if not 0 <= state['size'] <= 131072:
            raise ValueError('rtmp-control-message-bound')
        count = min(self.chunk_size, state['size'] - state['offset'])
        if len(data) < cursor + count:
            return None
        payload = bytes(data[cursor:cursor+count])
        state['offset'] = (state['offset'] + count) % max(1, state['size'])
        return cursor + count, channel, state, payload


# Run 68: csid=2, type=4, stream=0, UserControl event=6 (PingRequest).
PING = b'\x02\x00\x00\x00\x00\x00\x06\x04\x00\x00\x00\x00\x00\x06\x00\x00\x00\x01'
PAUSE_SECONDS = 6.


class FaultProxy:
    """Loopback-only sink; fault once globally, accept later writers at full speed."""

    def __init__(self, target, mode):
        parsed = urlsplit(target)
        if parsed.scheme != 'rtmp' or parsed.hostname != '127.0.0.1':
            raise ValueError('fixture-loopback-required')
        if mode not in ('full', 'fragmented', 'backpressure'):
            raise ValueError('fixture-mode')
        self.target = (parsed.hostname, parsed.port)
        self.mode = mode
        self.stopped = threading.Event()
        self.requested = threading.Event()
        self.injected = threading.Event()
        self.completed = threading.Event()
        self.pause = threading.Event()
        self.pause_started = threading.Event()
        self.connections = 0
        self.forwarded_bytes = 0
        self.injected_at = self.pause_at = self.finished_at = None
        self.error_code = None
        self.sockets, self.threads = [], []
        self.lock = threading.Lock()
        self.listener = socket.socket()
        # This bound is applied ONLY to our loopback listener, before accept.
        if mode == 'backpressure':
            self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        self.receive_buffer = self.listener.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        self.listener.bind(('127.0.0.1', 0))
        self.port = self.listener.getsockname()[1]
        self.listener.listen(4)
        self.listener.settimeout(.05)
        self.url = urlunsplit(parsed._replace(netloc=f'127.0.0.1:{self.port}'))
        self.thread = threading.Thread(target=self._accept, name='recovery-fixture-listener')
        self.thread.start()

    @staticmethod
    def _shutdown(connection):
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _accept(self):
        while not self.stopped.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.connections += 1
            number = self.connections
            with self.lock:
                # The first socket can still hold queued bytes during its
                # six-second pause. Retire that old publisher when a new one
                # arrives, so MediaMTX's single-publisher policy is not itself
                # a second injected fault. The original pause timer continues.
                if number > 1:
                    for previous in self.sockets:
                        self._shutdown(previous)
                self.sockets.append(client)
            worker = threading.Thread(target=self._connection, args=(client, number),
                                      name=f'recovery-fixture-connection-{number}')
            self.threads.append(worker)
            worker.start()

    def _connection(self, client, number):
        done = threading.Event()
        upstream = reader = None
        try:
            upstream = socket.create_connection(self.target, timeout=2)
            client.settimeout(2)
            upstream.settimeout(2)
            with self.lock:
                self.sockets.append(upstream)
            reader = threading.Thread(target=self._controls, args=(client, upstream, done, number),
                                      name=f'recovery-fixture-control-{number}')
            reader.start()
            while not (self.stopped.is_set() or done.is_set()):
                throttled = number == 1 and self.mode == 'backpressure' and self.requested.is_set()
                if throttled and self.pause.is_set() and not self.pause_started.is_set():
                    self.pause_at = time.monotonic()
                    self.pause_started.set()
                    # Do not shorten the fault when the first writer is reaped.
                    if self.stopped.wait(PAUSE_SECONDS):
                        break
                    self.finished_at = time.monotonic()
                    self.completed.set()
                if not select.select([client], [], [], .02)[0]:
                    continue
                data = client.recv(64 if throttled and not self.completed.is_set() else 65536)
                if not data:
                    break
                upstream.sendall(data)
                self.forwarded_bytes += len(data)
                if throttled and not self.completed.is_set():
                    self.stopped.wait(.02)
        except OSError:
            # A failed/reaped publisher closes its own connection. The listener
            # must stay alive so the replacement writer can really reconnect.
            pass
        except Exception:
            self.error_code = 'fixture-media-failed'
        finally:
            done.set()
            self._shutdown(client)
            if upstream is not None:
                self._shutdown(upstream)
            if reader is not None:
                reader.join(timeout=3)
                if reader.is_alive():
                    self.error_code = 'fixture-control-survived'
            client.close()
            if upstream is not None:
                upstream.close()

    def _controls(self, client, upstream, done, number):
        gate = MessageGate()
        try:
            while not (self.stopped.is_set() or done.is_set()):
                if (number == 1 and self.mode != 'backpressure' and self.requested.is_set()
                        and not self.injected.is_set() and gate.at_boundary):
                    client.sendall(PING[:1] if self.mode == 'fragmented' else PING)
                    self.injected_at = time.monotonic()
                    self.injected.set()
                    if self.mode == 'fragmented':
                        if self.stopped.wait(PAUSE_SECONDS):
                            break
                        # A correctly reaped first writer may already be gone.
                        try:
                            client.sendall(PING[1:])
                        except OSError:
                            pass
                    self.finished_at = time.monotonic()
                    self.completed.set()
                if not select.select([upstream], [], [], .02)[0]:
                    continue
                data = upstream.recv(65536)
                if not data:
                    break
                for complete in gate.feed(data):
                    client.sendall(complete)
        except OSError:
            pass
        except Exception:
            self.error_code = 'fixture-control-failed'
        finally:
            done.set()
            self._shutdown(client)
            self._shutdown(upstream)

    def close(self):
        self.stopped.set()
        self.listener.close()
        with self.lock:
            for connection in self.sockets:
                self._shutdown(connection)
        self.thread.join(timeout=2)
        for worker in self.threads:
            worker.join(timeout=4)
        self.url = None
        if self.thread.is_alive() or any(worker.is_alive() for worker in self.threads):
            raise RuntimeError('fixture-thread-survived')


class NoOpMotion:
    """Identity only for synthetic coverage; this makes no motion-quality claim."""

    def add(self, index, pixels):
        pass

    def project_many(self, quads, source_index, target_index, deadline=None):
        return list(quads)


def engine(delay=.01):
    return MaskingEngine({name: DetectorLane(name, NoOpDetector(), 120)
                          for name in ('fast', 'accurate')},
                         {'fps': 30, 'delay_seconds': delay}, motion=NoOpMotion())


class LocalSink:
    """Reuse verified MediaMTX; config/credentials travel through private pipes."""

    def __init__(self, mode):
        self.phone, self.internal = Credentials.generate(), Credentials.generate()
        self.secrets = (self.phone.user, self.phone.password, self.internal.user, self.internal.password)
        self.stack = ExitStack()
        try:
            # Reserve disjoint ports together, release immediately before MTX
            # binds. TCP and UDP have separate port spaces.
            with ExitStack() as reservations:
                sockets = [reservations.enter_context(socket.socket(socket.AF_INET, kind))
                           for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM, socket.SOCK_STREAM)]
                for reservation in sockets:
                    reservation.bind(('127.0.0.1', 0))
                self.ports = [reservation.getsockname()[1] for reservation in sockets]
            self.address = RelayAddress('127.0.0.1', *self.ports)
            self.server = self.stack.enter_context(MediaMTX(self.address, self.phone, self.internal))
            self.pid = self.server.process.pid
            self.proxy = FaultProxy(self.address.rtmp('shielded', self.internal), mode)
            self.stack.callback(self.proxy.close)
        except BaseException:
            self.stack.close()
            raise

    def close(self):
        self.stack.close()


def safe_failure(error, output):
    """No upstream exception text, URL, or unbounded object repr enters receipts."""
    details = output.error_details or {}
    return {'error_class': type(error).__name__, 'code': output.error_code,
            **{key: details[key] for key in ('operation', 'active_frame_index',
                'completed_frame_index', 'operation_age_seconds') if key in details}}


def child_pids():
    return {child.pid for child in multiprocessing.active_children()}


def record(test, receipt, secrets=()):
    serialized = json.dumps(receipt, sort_keys=True)
    # Check before either persistence or diagnostic assertion can print it.
    test.assertTrue(all(value not in serialized for value in secrets), 'fixture-credential-leak')
    destination = os.environ.get('M2_RECOVERY_RECEIPTS')
    if destination:
        path = Path(destination)
        path.mkdir(parents=True, exist_ok=True)
        (path / (test._testMethodName + '.json')).write_text(serialized + '\n')
    return serialized
