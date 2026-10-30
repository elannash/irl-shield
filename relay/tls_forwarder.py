"""Bounded loopback RTMP to verified TLS; never owns an RTMP key or URL."""
import select
import socket
import ssl
import threading
import time


class TLSForwarder:
    """One local listener survives writer reconnects; each TLS peer is verified.

    Production uses system CAs. A private CA file supports explicitly configured
    trust, including the synthetic loopback certificate fixture. An RTMP session
    EOF closes both sockets; buffered media is never replayed on a new connection.
    """
    capacity = 2

    def __init__(self, host='live.twitch.tv', port=443, *, cafile=None):
        if not isinstance(host, str) or not host or any(c in host for c in '/@:?\r\n\x00'):
            raise ValueError('Invalid TLS peer hostname')
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid TLS peer port')
        self.host, self.peer_port = host, port
        self.context = ssl.create_default_context(cafile=cafile)
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._sockets = set()
        self._workers = set()
        self.listener = self.thread = None
        self.port = None
        self._stats = {'connections': 0, 'failures': 0, 'rejected': 0, 'last_error': None}

    @property
    def stats(self):
        with self._lock:
            return dict(self._stats)

    def __enter__(self):
        if self.listener is not None or self._stopped.is_set():
            raise RuntimeError('TLS forwarder cannot be restarted')
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.listener.bind(('127.0.0.1', 0))
            self.listener.listen(self.capacity)
            self.listener.settimeout(.2)
            self.port = self.listener.getsockname()[1]
            self.thread = threading.Thread(target=self._accept, name='verified-tls-listener')
            self.thread.start()
        except BaseException:
            self.listener.close()
            raise
        return self

    def _accept(self):
        while not self._stopped.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self._lock:
                if self._stopped.is_set() or len(self._workers) >= self.capacity:
                    client.close()
                    self._stats['rejected'] += 1
                    continue
                self._sockets.add(client)
                self._stats['connections'] += 1
                worker = threading.Thread(target=self._serve, args=(client,), name='verified-tls-connection')
                self._workers.add(worker)
                worker.start()

    def _serve(self, client):
        peer = raw = None
        try:
            client.settimeout(5)
            raw = socket.create_connection((self.host, self.peer_port), timeout=5)
            with self._lock:
                if self._stopped.is_set():
                    return
                self._sockets.add(raw)
            # Register before handshake so shutdown can interrupt an unfinished
            # TLS exchange. No RTMP byte is forwarded before verification.
            peer = self.context.wrap_socket(raw, server_hostname=self.host, do_handshake_on_connect=False)
            with self._lock:
                self._sockets.discard(raw)
                self._sockets.add(peer)
                stopped = self._stopped.is_set()
            if stopped:
                return
            peer.do_handshake()
            self._pipe(client, peer)
        except ssl.SSLCertVerificationError:
            self._failed('tls-verification-failed')
        except (OSError, ssl.SSLError):
            if not self._stopped.is_set():
                self._failed('tls-forwarding-failed')
        finally:
            for connection in (client, peer, raw):
                if connection is not None:
                    with self._lock:
                        self._sockets.discard(connection)
                    connection.close()
            with self._lock:
                self._workers.discard(threading.current_thread())

    def _failed(self, code):
        with self._lock:
            self._stats['failures'] += 1
            self._stats['last_error'] = code

    def _pipe(self, client, peer):
        while not self._stopped.is_set():
            readable, _, _ = select.select([client, peer], [], [], 0 if peer.pending() else .2)
            if peer.pending() and peer not in readable:
                readable.append(peer)
            for source in readable:
                data = source.recv(65536)
                if not data:
                    return
                (peer if source is client else client).sendall(data)

    def close(self):
        self._stopped.set()
        if self.listener is not None:
            self.listener.close()
        with self._lock:
            sockets = list(self._sockets)
            workers = list(self._workers)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        deadline = time.monotonic() + 6
        for worker in ([self.thread] if self.thread else []) + workers:
            worker.join(max(0, deadline - time.monotonic()))
        if any(worker.is_alive() for worker in ([self.thread] if self.thread else []) + workers):
            raise RuntimeError('TLS forwarder did not stop')

    def __exit__(self, *error):
        self.close()
