"""Device event accounting. Host timestamps select windows; they are never GPU cost."""
import math
import time

EVENT_SCOPE = ('CUDA event elapsed on the verified ORT user compute stream around synchronous session.run. '
               'Includes stream-ordered copies/waits and device-timeline idle host gaps inside run; '
               'excludes preprocessing, postprocessing, pre-start stream synchronization, NVENC cost and other streams. '
               'Not kernel-only time, GPU occupancy or total-device utilization. Overlapping lane intervals may overlap.')


class EventTimer:
    def __init__(self, events, *, lane):
        self.events, self.lane = events, lane
        self.rows = []

    def run(self, inference, *args, **kwargs):
        row = {'call': len(self.rows), 'lane': self.lane, 'host_started_at': time.monotonic(),
               'start_recorded': False, 'end_recorded': False, 'wait_completed': False,
               'inference_completed': False, 'device_ms': None, 'errors': []}
        self.rows.append(row)
        failure = None
        try:
            self.events.prepare()
            self.events.record('start')
            row['start_recorded'] = True
            value = inference(*args, **kwargs)
            row['inference_completed'] = True
        except BaseException as error:
            failure = error
            row['errors'].append(f'{type(error).__name__}: {error}')
        finally:
            # Even failed inference can leave queued kernels; drain before accepting or reusing events.
            if row['start_recorded']:
                try:
                    self.events.record('end')
                    row['end_recorded'] = True
                    self.events.wait()
                    row['wait_completed'] = True
                    milliseconds = self.events.elapsed_ms()
                    if not math.isfinite(milliseconds) or milliseconds < 0:
                        raise ValueError('CUDA event duration must be finite and nonnegative')
                    row['device_ms'] = milliseconds
                except BaseException as error:
                    row['errors'].append(f'{type(error).__name__}: {error}')
                    if failure is None:
                        failure = error
            row['host_finished_at'] = time.monotonic()
        if failure is not None:
            raise failure
        return value


def summarize(rows, *, source_frames):
    if type(source_frames) is not int or source_frames <= 0:
        raise ValueError('GPU cost requires an explicit positive source-frame denominator')
    good = [r for r in rows if not r['errors'] and r['inference_completed'] and r['start_recorded']
            and r['end_recorded'] and r['wait_completed'] and r['device_ms'] is not None]
    valid = bool(rows) and len(good) == len(rows)
    total = sum(r['device_ms'] for r in good)
    return {'valid': valid, 'attempted_calls': len(rows), 'successful_calls': len(good),
            'failed_calls': len(rows) - len(good), 'source_frames': source_frames,
            'device_interval_sum_ms': total if valid else None,
            'gpu_ms_per_inference': total / len(rows) if valid else None,
            'gpu_ms_per_source_frame': total / source_frames if valid else None,
            'event_scope': EVENT_SCOPE}
