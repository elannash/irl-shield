"""Linux live relay; no Twitch login, key acquisition, or Twitch network egress."""
import argparse
import json
import math
from pathlib import Path
import signal
import sys
import threading
import time

from relay.live import RelaySession
from relay.mediamtx import MediaMTX
from relay.security import Credentials, RelayAddress
from relay.stream import Egress, NetworkInput
from shield.engine import MaskingEngine
from shield.lanes import DetectorLane


def make_engine(cache, provider='cuda', faults=()):
    from bench.onnx_detectors import create_detector
    lanes = {}
    try:
        for name, model, rate, width in (('fast', 'ppocr-v6-tiny', 8, 640),
                                        ('accurate', 'ppocr-v6-small', 4, 960)):
            backend = create_detector(model, {'provider': provider, 'threads': 2, 'cache_dir': cache,
                                              'limit_side_len': width})
            lanes[name] = DetectorLane(name, backend, rate, width=width,
                                       fault_intervals=faults if name == 'accurate' else ())
        return MaskingEngine(lanes, {'fps': 30, 'delay_seconds': 1., 'before': 6, 'after': 30,
                                    'motion_mode': 'phase', 'motion_width': 320,
                                    'motion_min_response': .05, 'padding': .3})
    except BaseException:
        for lane in lanes.values():
            lane.close()
        raise


def run(engine, address, phone, internal, directory, stopped, seconds=None,
        width=1280, height=720, encoder='h264_nvenc', control_ready=None):
    """M3's control_ready(callbacks) gets hold/set_stream_key; key stays in memory.

    This function owns engine lifetime. The caller owns MediaMTX and the stop
    event, and must never log the credentials it supplied.
    """
    source = output = None
    session = None
    summary = {'status': 'failed'}
    started = time.monotonic()
    try:
        output = Egress(address.rtmp('shielded', internal), directory, width, height, encoder)
        session = RelaySession(engine, output.write, width=width, height=height)
        if control_ready:
            control_ready(session.control)
        source = NetworkInput(address.rtsp('camera', internal))
        while not stopped.is_set() and (seconds is None or time.monotonic() - started < seconds):
            for kind, pts, value, generation, arrived in source.drain():
                if kind == 'video':
                    session.video(pts, value, generation, now=arrived)
                elif kind == 'audio':
                    session.audio(pts, value, generation)
                else:
                    session.disconnected()
            session.tick()
            stopped.wait(.005)
        summary['status'] = 'stopped'
    except Exception as error:
        summary['failure'] = {'error_class': type(error).__name__,
                              'message': 'Relay transport failed; upstream text suppressed',
                              'output_code': output.error_code if output is not None else None,
                              'encoder': output.error_details if output is not None else None,
                              'at_monotonic': time.monotonic(),
                              'input_code': source.error_code if source is not None else None}
        raise RuntimeError('Relay transport failed (upstream diagnostics suppressed)') from None
    finally:
        cleanup = []
        for resource in (source, engine, output):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    cleanup.append(type(resource).__name__)
        summary.update(seconds=time.monotonic() - started, cleanup_errors=cleanup,
                       session=session.stats if session else None,
                       input_queue_capacity=8, input_queue_high_water=source.high_water if source else None,
                       engine=engine.stats, output_frames=output.count if output else 0,
                       max_egress_write_seconds=output.max_write_seconds if output else None)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'runtime.json').write_text(json.dumps(summary, indent=2) + '\n')
        if cleanup:
            raise RuntimeError('Relay cleanup failed: ' + ','.join(cleanup)) from None
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='100.109.49.77')
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--model-cache', type=Path, default=Path('models/cache'))
    parser.add_argument('--phone-setup', action='store_true')
    parser.add_argument('--seconds', type=float)
    args = parser.parse_args()
    if args.seconds is not None and (not math.isfinite(args.seconds) or args.seconds <= 0):
        parser.error('A positive finite run duration is required')
    if args.phone_setup and not (sys.stdin.isatty() and sys.stdout.isatty()):
        parser.error('Phone credentials may only be displayed in an explicit interactive terminal')
    address = RelayAddress(args.host)
    phone, internal = Credentials.generate(), Credentials.generate()
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    with MediaMTX(address, phone, internal):
        engine = make_engine(args.model_cache)
        if args.phone_setup:
            # Exactly once, only by this explicit interactive action. Never put
            # these values in logs, process argv, saved setup or receipts.
            print('Moblin RTMP URL:', address.rtmp('camera', phone))
            print('Moblin SRT URL:', address.srt('publish', 'camera', phone))
            print('OBS RTMP:', address.rtmp('shielded'))
            print('OBS SRT:', address.srt('read', 'shielded'))
        run(engine, address, phone, internal, args.artifacts, stopped, args.seconds)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Relay failed; credentialed upstream diagnostics suppressed') from None
