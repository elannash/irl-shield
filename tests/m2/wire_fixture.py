"""Loopback TCP observation before TLS decoding, including rejected handshakes."""
import select
import socket
import threading
import time


class RawPeer:
    """Transparent TCP front for a loopback TLS fixture; records all client bytes.

    Inspection is available only after both accept and forwarding threads exit.
    Backend EOF never stops collection of later client bytes on that connection.
    """
    def __init__(self, upstream_port):
        self.upstream_port = upstream_port
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(8)
        self.listener.settimeout(.1)
        self.port = self.listener.getsockname()[1]
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._streams, self._workers, self._sockets = [], [], set()
        self.errors = []
        self.response_write_closed = 0
        self._closed = False
        self.thread = threading.Thread(target=self._accept, name='raw-tls-peer')
        self.thread.start()

    def _accept(self):
        while True:
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                if self._stop.is_set():
                    return
                continue
            except OSError:
                return
            wire = bytearray()
            with self._lock:
                self._streams.append(wire)
                self._sockets.add(client)
                worker = threading.Thread(target=self._pipe, args=(client, wire), name='raw-tls-wire')
                self._workers.append(worker)
            worker.start()

    def _pipe(self, client, wire):
        upstream = None
        try:
            upstream = socket.create_connection(('127.0.0.1', self.upstream_port), timeout=5)
            with self._lock:
                self._sockets.add(upstream)
            client.settimeout(2)
            upstream.settimeout(2)
            remote_open = True
            while True:
                ready, _, _ = select.select([client, upstream] if remote_open else [client], [], [], .1)
                if not ready and self._stop.is_set():
                    return
                for source in ready:
                    try:
                        data = source.recv(65536)
                    except ConnectionResetError:
                        data = b''
                    if source is client:
                        if not data:
                            return
                        wire.extend(data)
                        if remote_open:
                            try:
                                upstream.sendall(data)
                            except OSError:
                                remote_open = False
                    elif data:
                        try:
                            client.sendall(data)
                        except OSError:
                            # TLS alerts can reach us after a rejecting client
                            # closes. Keep collecting its remaining raw bytes.
                            self.response_write_closed += 1
                    else:
                        remote_open = False
                        try:
                            client.shutdown(socket.SHUT_WR)
                        except OSError:
                            pass
        except OSError as error:
            self.errors.append(type(error).__name__)
        finally:
            for connection in (client, upstream):
                if connection is not None:
                    with self._lock:
                        self._sockets.discard(connection)
                    connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self._stop.set()
        # Drain already connected clients before closing the listener. A post-
        # verification-failure reconnect may still be in its accept backlog.
        self.thread.join(5)
        self.listener.close()
        deadline = time.monotonic() + 5
        for worker in self._workers:
            worker.join(max(0, deadline - time.monotonic()))
        alive = [w for w in [self.thread, *self._workers] if w.is_alive()]
        if alive:
            with self._lock:
                sockets = list(self._sockets)
            for connection in sockets:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
            for worker in alive:
                worker.join(5)
            raise RuntimeError('Raw TCP capture did not finish normally')
        self._closed = True

    def rejection(self, canary):
        if not self._closed:
            raise RuntimeError('Raw peer inspection requires completed collection')
        streams = [bytes(s) for s in self._streams]
        types = []
        valid = bool(streams) and not self.errors
        for data in streams:
            position, records = 0, []
            while position < len(data):
                header = data[position:position+5]
                if len(header) != 5 or header[1] != 3 or header[2] not in (1, 2, 3):
                    valid = False
                    break
                kind, size = header[0], int.from_bytes(header[3:5], 'big')
                body = data[position+5:position+5+size]
                if not 0 < size <= 18432 or len(body) != size:
                    valid = False
                    break
                if not records:
                    valid = valid and kind == 0x16 and body[0] == 1
                else:
                    # TLS failure alerts (and compatibility CCS) may follow
                    # ClientHello; neither carries RTMP application bytes.
                    valid = valid and (kind == 0x15 or (kind == 0x14 and body == b'\x01'))
                records.append(kind)
                position += 5 + size
            valid = valid and position == len(data) and bool(records)
            types.append(records)
        return {'connections': len(streams), 'bytes_received': sum(map(len, streams)),
                'record_types': types, 'client_hello_and_controls_only': bool(valid),
                'canary_absent': all(canary not in data for data in streams),
                'capture_errors': list(self.errors), 'response_write_closed': self.response_write_closed}
