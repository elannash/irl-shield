"""Callable boundary spans, exclusive within a thread; never GPU kernel timings."""
from collections import defaultdict
import json
import os
from pathlib import Path
import sys
import threading
import time

STAGES = ('decode', 'colorconvert', 'resize', 'detector-pre', 'detector-infer',
          'detector-post', 'tracking', 'maskrender', 'encode', 'mux', 'ipc-copies')


class Ledger:
    def __init__(self, start, end, window=None):
        self.window = window
        self.start, self.end = start, end
        self.stacks = defaultdict(list)
        self.rows = []

    @property
    def start(self):
        return self.window[0] if self.window is not None else self._start

    @start.setter
    def start(self, value):
        if self.window is not None:
            self.window[0] = value
        self._start = value

    @property
    def end(self):
        return self.window[1] if self.window is not None else self._end

    @end.setter
    def end(self, value):
        if self.window is not None:
            self.window[1] = value
        self._end = value

    def enter(self, thread, token, stage, wall, cpu):
        self.stacks[thread].append([token, stage, wall, cpu, 0., 0.])

    def leave(self, thread, token, wall, cpu):
        stack = self.stacks[thread]
        if not stack or stack[-1][0] != token:
            raise RuntimeError('unbalanced measured span')
        _, stage, began, cpu_began, child_wall, child_cpu = stack.pop()
        elapsed, used = wall - began, cpu - cpu_began
        if stack:
            stack[-1][4] += elapsed
            stack[-1][5] += used
        window = ('steady' if self.start <= began <= wall <= self.end else
                  'startup' if wall < self.start else 'shutdown' if began > self.end else 'boundary')
        self.rows.append({'stage': stage, 'thread': thread, 'start': began, 'end': wall,
                          'wall_seconds': max(0., elapsed - child_wall),
                          'caller_cpu_seconds': max(0., used - child_cpu), 'window': window})


def summarize(rows, source_frames, seconds):
    table = {}
    for stage in STAGES:
        selected = [r for r in rows if r['stage'] == stage and r['window'] == 'steady']
        observed = bool(selected) and source_frames > 0 and seconds > 0
        cpu = sum(r['caller_cpu_seconds'] for r in selected)
        table[stage] = {
            'evidence_kind': 'measured-callable-span' if observed else 'unknown',
            'calls': len(selected),
            'wall_ms_per_source_frame': 1000 * sum(r['wall_seconds'] for r in selected) / source_frames if observed else None,
            'caller_thread_cpu_ms_per_source_frame': 1000 * cpu / source_frames if observed else None,
            'caller_thread_cpu_percent_one_core': 100 * cpu / seconds if observed else None,
            'h_to_d_count_per_source_frame': None, 'h_to_d_bytes_per_source_frame': None,
            'd_to_h_count_per_source_frame': None, 'd_to_h_bytes_per_source_frame': None,
        }
    return table


def select(frame, event, arg):
    """Recognize pinned code and C call boundaries without retaining arguments."""
    filename = frame.f_code.co_filename.replace('\\', '/')
    function = frame.f_code.co_name
    owner = frame.f_locals.get('self')
    cls = type(owner).__name__
    if event in ('call', 'return'):
        if filename.endswith('/shield/motion.py') and cls == 'MotionHistory' and function == 'add':
            return 'tracking'
        if filename.endswith('/shield/engine.py') and function == '_coverage_and_quads':
            return 'tracking'
        if filename.endswith('/shield/render.py') and function == 'render':
            return 'maskrender'
        if filename.endswith('/relay/stream.py') and function in ('_message', '_receive'):
            return 'ipc-copies'
        if '/rapidocr/ch_ppocr_det/' in filename and function == '__call__':
            return {'DetPreProcess': 'detector-pre', 'DBPostProcess': 'detector-post'}.get(cls)
        if '/onnxruntime/capi/onnxruntime_inference_collection.py' in filename and function == 'run':
            return 'detector-infer'
    if event.startswith('c_'):
        name = getattr(arg, '__name__', '')
        obj = getattr(arg, '__self__', None)
        if filename.endswith('/relay/stream.py'):
            if name == 'decode' and getattr(getattr(obj, 'stream', None), 'type', None) == 'video':
                return 'decode'
            if name == 'to_ndarray' and type(obj).__name__ == 'VideoFrame':
                return 'colorconvert'
            if name == 'from_ndarray' and function == 'write' and getattr(obj, '__name__', '') == 'VideoFrame':
                return 'colorconvert'
            if name == 'encode' and getattr(obj, 'type', None) == 'video':
                return 'encode'
            if name == 'mux':
                return 'mux'
        if '/shield/' in filename or '/rapidocr/ch_ppocr_det/' in filename:
            if name == 'resize':
                return 'resize'
            if name == 'cvtColor':
                return 'colorconvert'
    return None


class Profiler:
    def __init__(self, start, end, observe=None, window=None, instrument=True):
        self.ledger = Ledger(start, end, window)
        self.observe = observe
        self.instrument = instrument
        self.frames = []
        self.evidence = []
        self.calls = {}
        self.inferences = defaultdict(int)
        self.ipc_payloads = []
        self.errors = []

    def hook(self, frame, event, arg):
        try:
            thread = threading.get_ident()
            stage = select(frame, event, arg) if self.instrument else None
            if stage:
                token = (id(frame), event.startswith('c_'), getattr(arg, '__name__', None) if event.startswith('c_') else None)
                if event in ('call', 'c_call'):
                    self.ledger.enter(thread, token, stage, time.monotonic(), time.thread_time())
                elif event in ('return', 'c_return', 'c_exception'):
                    self.ledger.leave(thread, token, time.monotonic(), time.thread_time())
            filename = frame.f_code.co_filename.replace('\\', '/')
            if event == 'return' and filename.endswith('/relay/stream.py'):
                now = time.monotonic()
                if frame.f_code.co_name == '_timestamp' and frame.f_locals.get('kind') == 'video' and arg is not None:
                    row = {'kind': 'source', 'at': now, 'pts': float(arg), 'generation': frame.f_locals['generation']}
                    self.frames.append(row)
                    self.note(row)
                if frame.f_code.co_name in ('_message', '_receive'):
                    size = (len(frame.f_locals['data']) if frame.f_code.co_name == '_message' and 'data' in frame.f_locals
                            else frame.f_locals.get('size'))
                    if type(size) is int:
                        self.ipc_payloads.append({'at': now, 'operation': frame.f_code.co_name, 'serialized_bytes': size})
            function = frame.f_code.co_name
            owner = frame.f_locals.get('self')
            if filename.endswith('/onnxruntime/capi/onnxruntime_inference_collection.py') and function == 'run' and event == 'return' and arg is not None:
                self.inferences[thread] += 1
            if filename.endswith('/bench/onnx_detectors.py') and function == 'detect_quads':
                if event == 'call':
                    self.calls[id(frame)] = self.inferences[thread]
                elif event == 'return':
                    previous = self.calls.pop(id(frame), self.inferences[thread])
                    if arg is not None and self.inferences[thread] > previous:
                        source = frame.f_back.f_locals.get('frame') if frame.f_back else None
                        self.note({'kind': 'detector', 'at': time.monotonic(),
                                   'lane': threading.current_thread().name.removeprefix('shield-'),
                                   'inference_completed': True, 'index': getattr(source, 'index', None),
                                   'pts': getattr(source, 'pts', None)})
            if filename.endswith('/relay/stream.py') and type(owner).__name__ == 'Egress' and function == 'write':
                if event == 'call':
                    self.calls[id(frame)] = owner.count
                elif event == 'return':
                    previous = self.calls.pop(id(frame), owner.count)
                    result = frame.f_locals.get('result')
                    if owner.count > previous and result is not None:
                        self.note({'kind': 'encoded', 'at': time.monotonic(), 'index': result.index,
                                   'pts': result.pts, 'generation': owner.generation,
                                   'state': result.state, 'slate': bool(result.slate)})
            if filename.endswith('/relay/live.py') and function == 'video' and event == 'return' and owner is not None:
                self.note({'kind': 'ingested', 'at': time.monotonic(), 'index': owner.last_index,
                           'pts': frame.f_locals.get('pts'), 'generation': owner.generation})
            if filename.endswith('/multiprocessing/process.py') and function == 'close' and event == 'call' and getattr(owner, 'name', None) == 'm2-egress':
                self.note({'kind': 'encoder-exit', 'at': time.monotonic(), 'pid': owner.pid,
                           'exitcode': owner.exitcode, 'alive': owner.is_alive()})
        except Exception as error:
            # A profiler error cannot alter privacy or transport decisions.
            if len(self.errors) < 20:
                self.errors.append(type(error).__name__)

    def note(self, row):
        self.evidence.append(row)
        if self.observe is not None:
            self.observe(row)

    def start(self):
        sys.setprofile(self.hook)
        threading.setprofile(self.hook)

    def close(self, directory, role):
        sys.setprofile(None)
        threading.setprofile(None)
        data = {'pid': os.getpid(), 'role': role, 'start': self.ledger.start, 'end': self.ledger.end,
                'rows': self.ledger.rows, 'source_frames': self.frames, 'evidence': self.evidence, 'ipc_payloads': self.ipc_payloads,
                'errors': self.errors, 'unfinished_spans': sum(len(v) for v in self.ledger.stacks.values()),
                'cpu_scope': 'Calling thread only; native worker threads excluded. Wall spans include waits.',
                'overlap': 'Nested selected spans subtracted within thread; concurrent threads/processes overlap.'}
        path = Path(directory) / f'spans-{role}-{os.getpid()}.json'
        path.write_text(json.dumps(data, separators=(',', ':')) + '\n')


def encode_worker_profiled(*args, window, directory, instrument=True):
    """Picklable opt-in wrapper; production target and behavior stay intact."""
    from relay.stream import _encode_worker
    profiler = Profiler(window[0], window[1], window=window, instrument=instrument)
    profiler.start()
    try:
        _encode_worker(*args)
    finally:
        profiler.close(directory, 'encoder')
