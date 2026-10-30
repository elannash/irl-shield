"""Independent reconnecting SRT MPEG-TS capture; never remux raw timestamps."""
from collections import deque
import hashlib
import json
from pathlib import Path
import threading
import time

from relay.native_auth import SRT


class Capture:
    def __init__(self, url, directory):
        self.url, self.directory = url, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.stopped = threading.Event()
        self.stats = {'opened': False, 'packets': 0, 'bytes': 0, 'connections': 0,
                      'startup_retries': 0, 'receive_failures': 0, 'status': 'pending'}
        self.events = deque(maxlen=64)
        self.segments = []
        self.thread = threading.Thread(target=self._read, name='srt-capture', daemon=True)
        self.thread.start()

    def _read(self):
        srt = None
        try:
            srt = SRT()
            with (self.directory / 'packets.jsonl').open('w') as packets:
                while not self.stopped.is_set():
                    phase, segment = 'connect', None
                    try:
                        with srt.connection(self.url) as fd:
                            if self.stopped.is_set():
                                break
                            generation = self.stats['connections'] + 1
                            name = f'network-{generation:04d}.ts'
                            segment = {'generation': generation, 'file': name, 'packets': 0,
                                       'bytes': 0, 'started_monotonic': time.monotonic()}
                            self.segments.append(segment)
                            self.stats.update(opened=True, connections=generation, status='reading')
                            phase = 'receive'
                            with (self.directory / name).open('wb') as output:
                                while not self.stopped.is_set():
                                    payload = srt.receive(fd)
                                    if len(payload) % 188 or payload[0] != 0x47:
                                        raise ValueError('srt-mpegts-framing')
                                    output.write(payload)
                                    record = {'generation': generation, 'bytes': len(payload),
                                              'sha256': hashlib.sha256(payload).hexdigest(),
                                              'received_monotonic': time.monotonic()}
                                    packets.write(json.dumps(record) + '\n')
                                    for stats in (self.stats, segment):
                                        stats['packets'] += 1
                                        stats['bytes'] += len(payload)
                    except Exception as error:
                        self.stats['startup_retries' if phase == 'connect' else 'receive_failures'] += 1
                        self.events.append({'code': 'srt-' + phase, 'error_class': type(error).__name__,
                                            'at_monotonic': time.monotonic(),
                                            'generation': self.stats['connections']})
                    finally:
                        if segment is not None:
                            segment['finished_monotonic'] = time.monotonic()
                    self.stopped.wait(.1)
        except Exception as error:
            self.stats.update(status='failed', error_class=type(error).__name__)
        finally:
            if srt is not None:
                try:
                    srt.close()
                except Exception as error:
                    self.stats.update(status='failed', error_class=type(error).__name__)
            if self.stats['status'] != 'failed':
                self.stats['status'] = 'closed'
            self.stats['finished_monotonic'] = time.monotonic()

    def close(self):
        self.stopped.set()
        self.thread.join(7)
        if self.thread.is_alive():
            raise RuntimeError('srt-capture-close-timeout')
        self.url = None
        value = dict(self.stats, segments=self.segments, recent_events=list(self.events))
        (self.directory / 'transport.json').write_text(json.dumps(value, indent=2) + '\n')
