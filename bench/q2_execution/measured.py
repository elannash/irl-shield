"""Explicit detector adapter reusing production model verification and RapidOCR.

Changing the ORT stream and synchronizing each event interval can change scheduling.
These costs remain diagnostic until paired provider/output parity is established.
"""
import hashlib
import time

from bench.q2_execution.events import EventTimer


class MeasuredDetector:
    def __init__(self, detector, events, timer, session, original_run):
        self.detector, self.events, self.timer = detector, events, timer
        self.session, self.original_run = session, original_run
        self.metadata = detector.metadata
        self.calls = []
        self.closed = False

    def detect_quads(self, pixels):
        row = {'call': len(self.calls), 'host_started_at': time.monotonic(),
               'input_shape': list(pixels.shape), 'error': None}
        self.calls.append(row)
        try:
            quads = self.detector.detect_quads(pixels)
            import json
            row['output_quads_sha256'] = hashlib.sha256(json.dumps(quads, sort_keys=True).encode()).hexdigest()
            return quads
        except BaseException as error:
            row['error'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            row['host_finished_at'] = time.monotonic()

    def close(self):
        if self.closed:
            return
        self.detector.close()
        self.session.run = self.original_run
        self.session = self.original_run = None
        self.events.close()
        self.closed = True


class MeasuredBackends:
    def __init__(self, cudart):
        self.cudart, self.backends = cudart, {}

    def __call__(self, lane, name, options):
        from bench.independence import candidate_metadata
        from bench.onnx_detectors import PPOCRDetector, COMMON_OPTIONS, DETECTOR_NAMES, _session
        from bench.q2_execution.cuda import CudaEvents
        from bench.q2_execution.adapters import sha256
        from rapidocr.ch_ppocr_det.utils import DetPreProcess
        import numpy as np
        candidate_metadata(name)
        if name not in DETECTOR_NAMES or options.get('provider') != 'cuda' or not options.get('static_model'):
            raise ValueError('GPU cost adapter requires a registered static CUDA detector')
        params = {key: value for key, value in options.items() if key in COMMON_OPTIONS}
        height, width = options['input_size']
        scale = options.get('detect_width', width) / width
        small = np.zeros((int(height * scale), int(width * scale), 3), np.uint8)
        tensor = DetPreProcess(options.get('limit_side_len', 960), 'max')(small)
        if tensor is None:
            raise RuntimeError('Static preprocessing shape failed')
        params['static_shape'] = list(tensor.shape[2:])
        events = CudaEvents(self.cudart)
        timer = EventTimer(events, lane=lane)
        sessions = []
        def session_factory(model, model_options):
            session, metadata, artifact = _session(model, model_options, user_compute_stream=events.stream.value)
            original_run = session.run
            def measured_run(*args, **kwargs):
                feeds = args[1] if len(args) > 1 else kwargs['input_feed']
                inputs = {key: {'shape': list(value.shape), 'dtype': str(value.dtype),
                                'sha256': hashlib.sha256(value.tobytes()).hexdigest()} for key, value in feeds.items()}
                try:
                    return timer.run(original_run, *args, **kwargs)
                finally:
                    timer.rows[-1]['inputs'] = inputs
            session.run = measured_run
            sessions.append((session, original_run))
            metadata.update({'actual_model_sha256': sha256(metadata['model_path']),
                             'cuda_runtime_version': events.runtime_version,
                             'compute_capability': events.capability,
                             'stream_flags': 'cudaStreamNonBlocking',
                             'stream_pointer': events.stream.value,
                             'measurement_changes_scheduling': True,
                             'provider_output_parity_required': True})
            return session, metadata, artifact
        try:
            detector = PPOCRDetector(name, params, session_factory=session_factory)
        except BaseException:
            for session, original in sessions:
                session.run = original
            events.close()
            raise
        session, original = sessions[0]
        backend = MeasuredDetector(detector, events, timer, session, original)
        self.backends[lane] = backend
        return backend

    def close(self):
        errors = []
        for backend in self.backends.values():
            try:
                backend.close()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup('Measured detector cleanup failed', errors)
