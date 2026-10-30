"""Original CC0 loopback certificates and echo bytes; never real credentials."""
from pathlib import Path
import socket
import ssl
import subprocess
import threading


def certificates(directory):
    root = Path(directory)
    for name, san in (('peer', 'IP:127.0.0.1'), ('other', 'IP:127.0.0.1'),
                      ('wrong', 'DNS:wrong.invalid')):
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
            '-days', '1', '-subj', '/CN=synthetic-loopback', '-addext', 'subjectAltName=' + san,
            '-keyout', str(root / (name + '.key')), '-out', str(root / (name + '.crt'))],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    return root


class EchoTLS:
    def __init__(self, root, name='peer'):
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(root / (name + '.crt'), root / (name + '.key'))
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(4)
        self.listener.settimeout(.1)
        self.port = self.listener.getsockname()[1]
        self.stopped = threading.Event()
        self.received = []
        self.active = None
        self.thread = threading.Thread(target=self.serve, name='synthetic-tls-echo')
        self.thread.start()

    def serve(self):
        while not self.stopped.is_set():
            try:
                raw, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                raw.settimeout(2)
                with self.context.wrap_socket(raw, server_side=True) as peer:
                    self.active = peer
                    while not self.stopped.is_set():
                        data = peer.recv(65536)
                        if not data:
                            break
                        self.received.append(data)
                        peer.sendall(data)
            except (OSError, ssl.SSLError):
                raw.close()
            finally:
                self.active = None

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.stopped.set()
        self.listener.close()
        if self.active:
            try:
                self.active.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.thread.join(3)
        if self.thread.is_alive():
            raise RuntimeError('Synthetic TLS fixture survived')
