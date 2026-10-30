"""CC0 synthetic H.264 B-frame/AAC transport fixtures; no text or music."""
import socket
import threading
import time


from relay.srt_fixture import mpegts

class TCPVideo:
    """One real connection carries TS segments, then stays open until teardown."""
    def __init__(self, segments, seconds=3):
        self.segments = segments
        self.seconds = seconds
        self.stopped = threading.Event()
        self.finished = threading.Event()
        self.errors = []
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.listener.settimeout(.1)
        self.url = f'tcp://127.0.0.1:{self.listener.getsockname()[1]}'
        self.thread = threading.Thread(target=self._run, name='srt-fixture-tcp')
        self.thread.start()

    def _run(self):
        try:
            connection = None
            while not self.stopped.is_set() and connection is None:
                try:
                    connection, _ = self.listener.accept()
                except socket.timeout:
                    continue
            if connection is None:
                return
            with connection:
                connection.settimeout(1)
                for segment in self.segments:
                    origin = time.monotonic()
                    for offset in range(0, len(segment), 1316):
                        if self.stopped.wait(max(0, origin + self.seconds * offset / len(segment) - time.monotonic())):
                            return
                        connection.sendall(segment[offset:offset + 1316])
                self.finished.set()
                self.stopped.wait(10)
        except Exception as error:
            if not self.stopped.is_set():
                self.errors.append(type(error).__name__)

    def close(self):
        self.stopped.set()
        self.thread.join(3)
        self.listener.close()
        if self.thread.is_alive():
            raise RuntimeError('synthetic-publisher-close-timeout')


def local_server():
    from relay.mediamtx import MediaMTX, verified_binary
    from relay.security import Credentials, RelayAddress
    holders = []
    try:
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM, socket.SOCK_STREAM):
            holder = socket.socket(socket.AF_INET, kind)
            holder.bind(('127.0.0.1', 0))
            holders.append(holder)
        ports = [holder.getsockname()[1] for holder in holders]
    finally:
        for holder in holders:
            holder.close()
    address = RelayAddress('127.0.0.1', *ports)
    phone, internal = Credentials.generate(), Credentials.generate()
    binary = verified_binary()
    return MediaMTX(address, phone, internal, binary), address, phone, internal


class SRTPublisher:
    def __init__(self, url, payload):
        import multiprocessing
        import tempfile
        from pathlib import Path
        from relay.srt_replay import publish
        scratch = Path('/tmp/agents/irl-shield/srt-tests')
        scratch.mkdir(parents=True, exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(dir=scratch)
        path = Path(self.scratch.name)
        fixture = path / 'source.ts'
        fixture.write_bytes(payload)
        self.result = None
        self.receipt = path / 'publisher.json'
        context = multiprocessing.get_context('spawn')
        self.stopped = context.Event()
        self.process = context.Process(target=publish, name='synthetic-srt-publisher',
                                       args=(url, str(fixture), str(self.receipt), 1, self.stopped))
        self.process.start()

    @property
    def errors(self):
        import json
        if self.result is not None:
            return [] if self.result['status'] == 'stopped' else [self.result]
        if self.process.is_alive():
            return []
        if not self.receipt.exists():
            return ['publisher-no-receipt']
        value = json.loads(self.receipt.read_text())
        return [] if value['status'] == 'stopped' else [value]

    def close(self):
        if self.process.is_alive():
            self.stopped.set()
        self.process.join(4)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(3)
            raise RuntimeError('synthetic-srt-publisher-close-timeout')
        if self.receipt.exists():
            import json
            self.result = json.loads(self.receipt.read_text())
        self.scratch.cleanup()
