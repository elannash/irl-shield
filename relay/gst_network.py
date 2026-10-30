"""Finite localhost SRT flash/beep control through the unchanged engine.

Uses the authored CC0 control from relay.gst_av. Network receipts require every
encoded video frame and both independent media events; this is not a sustained
performance or detector-privacy score. The caller owns the host EX lease.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import threading
import time

import numpy as np

from bench.clocked_pipeline import drive, perf_health, probe_media
from relay.gst import GstSource, GstSink, quoted
from relay.gst_av import observe
from relay.gst_bench import engine_for
from relay.gst_native import Pipeline


def _port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def run(source_file, directory, encoder, decoder, *, contended=False):
    source_file, directory = Path(source_file).resolve(), Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    start = perf_health()
    (directory / 'preflight.json').write_text(json.dumps(start, indent=2) + '\n')
    if start['pressure_state'] != 'normal' and not contended:
        raise RuntimeError('Reject SRT control: memory pressure is ' + start['pressure_state'])
    media = probe_media(source_file)
    incoming, outgoing = _port(), _port()
    receiver_description = (
        f'srtsrc uri="srt://127.0.0.1:{outgoing}?mode=listener" auto-reconnect=false keep-listening=false ! '
        'tsdemux name=demux ignore-pcr=true '
        'demux. ! queue ! h264parse ! mux.video_0 '
        'demux. ! queue ! aacparse ! mux.audio_0 '
        f'mp4mux name=mux ! filesink location={quoted(directory / "received.mp4")}')
    # Pace elementary streams before mux; muxed TS buffers need not carry a
    # useful scheduling timestamp. An unpaced file would test an ingest burst.
    sender_description = (
        f'filesrc location={quoted(source_file)} ! qtdemux name=demux '
        'demux.video_0 ! queue ! h264parse ! identity sync=true ! mux. '
        'demux.audio_0 ! queue ! aacparse ! identity sync=true ! mux. '
        f'mpegtsmux name=mux alignment=7 ! srtsink uri="srt://127.0.0.1:{incoming}?mode=caller" sync=false')
    source = GstSource(f'srt://127.0.0.1:{incoming}?mode=listener', media, decoder=decoder,
                       detector_widths=(640, media['resolution'][0]), audio=True)
    sink = GstSink(f'srt://127.0.0.1:{outgoing}?mode=caller', media['resolution'], media['fps'],
                   encoder=encoder, audio=True, audio_source=source, artifacts=directory / 'relay.mp4')
    width, height = media['resolution']
    options = {'fps': media['fps'], 'delay_seconds': 1., 'fast_width': 640, 'accurate_width': width,
               'fast_rate_hz': 30., 'accurate_rate_hz': 30., 'motion_min_response': .05}
    warm = np.zeros((height, width, 3), np.uint8)
    copies = {w: np.zeros((round(height * w / width), w, 3), np.uint8) for w in source.widths}
    with ExitStack() as stack:
        engine, loading = engine_for(source, 'unmasked', options, warm, copies, stack)
    sender = None
    sender_errors = []

    def publish():
        try:
            until = time.monotonic() + 15
            while source.pipeline is None and not source.finished.is_set() and time.monotonic() < until:
                time.sleep(.01)
            if source.pipeline is None:
                raise TimeoutError('Source listener did not start')
            sender.start()
            sender.end([], timeout=20.)
            if not source.finished.wait(media['duration'] + 10):
                raise TimeoutError('Finite source did not drain before publisher shutdown')
        except Exception as error:
            sender_errors.append(error)
        finally:
            try:
                if sender is not None:
                    sender.close()
            except Exception as error:
                sender_errors.append(error)

    publishing = threading.Thread(target=publish, name='gst-control-publisher')
    commands = {'sender': sender_description, 'receiver': receiver_description,
                'source': source.description(), 'sink': sink.command, 'loading': loading}
    (directory / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    publishing_started = driven = False
    try:
        sender = Pipeline(sender_description)
        with Pipeline(receiver_description) as receiver:
            publishing.start()
            publishing_started = driven = True
            result = drive(source, engine, sink)
            result.update(input_arrivals=source.arrivals, input_timestamps=source.original_timestamps,
                          input_queue_drops=source.queue_drops)
            (directory / 'relay-result.json').write_text(json.dumps(result, indent=2) + '\n')
            publishing.join(25)
            if publishing.is_alive():
                raise RuntimeError('Publisher thread did not exit')
            if sender_errors:
                raise sender_errors[0]
            receiver.end([], timeout=10.)
    finally:
        # A native bus must outlive any thread blocked inside its end call.
        if publishing_started:
            publishing.join(25)
            if publishing.is_alive():
                raise RuntimeError('Publisher survived its bounded end call')
        if sender is not None:
            sender.close()
        if not driven:
            engine.close()
        (directory / 'input-timestamps.json').write_text(json.dumps(source.original_timestamps, indent=2) + '\n')
        (directory / 'end-health.json').write_text(json.dumps(perf_health(), indent=2) + '\n')
    before, after = observe(source_file), observe(directory / 'received.mp4')
    if after['media']['frames'] != result['frames']:
        raise RuntimeError('Received SRT frame count differs from actual encoded output')
    receipt = {**commands, 'frames': result['frames'], 'received_frames': after['media']['frames'],
               'protected_fraction': result['protected_fraction'], 'source': before, 'received': after,
               'perf_health': {'start': start, 'end': perf_health()}, 'performance_valid': False,
               'contended': contended,
               'introduced_av_offset_seconds': (np.asarray(after['audio_minus_video_seconds']) -
                                               before['audio_minus_video_seconds']).tolist(),
               'scope': '4s localhost SRT control; no sustained performance or detector-privacy claim'}
    (directory / 'network-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
