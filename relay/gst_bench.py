"""Lane-local GStreamer measurements using the existing sustained/quality schema.

The common engine, scorer and benchmark files remain unmodified. Readiness and
host locking belong to the CLI in relay.gst_run, before this module loads models.
"""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import time

import cv2

from bench import clocked_pipeline as clocked
from bench.pipeline import detector_for
from relay.gst import CopyLane, GstSource, GstSink
from relay.gst_native import Pipeline
from shield.engine import MaskingEngine
from shield.lanes import DetectorLane
from shield.render import Renderer

ROOT = Path(__file__).resolve().parents[1]


def transport_fingerprint():
    digest = hashlib.sha256()
    for path in sorted((ROOT / 'relay').glob('gst*.py')):
        digest.update(path.name.encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()


def warm_source(source):
    with Pipeline(source.description()) as pipeline:
        frame = pipeline.pull('frames', 10.)
        if frame is None:
            raise RuntimeError('GStreamer has no warmup video frame')
        copies = {}
        for width in source.widths:
            if width == source.media['resolution'][0]:
                copies[width] = frame.pixels
                continue
            reduced = pipeline.pull(f'copy{width}', 3.)
            if reduced is None or reduced.pts_ns != frame.pts_ns:
                raise RuntimeError('Warmup detector copies have mismatched PTS')
            copies[width] = reduced.pixels
        return frame.pixels, copies


def engine_for(source, candidate, options, warm, copies, stack):
    """Construct canonical detector workers; only the offered pixel adapter varies."""
    width, height = source.media['resolution']
    lanes, loading = {}, {}
    fast = candidate if candidate in ('unmasked', 'slate') else options.get('fast_candidate', 'ppocr-v6-tiny')
    for name, model, rate, pixels_w, side, provider in (
        ('fast', fast, options.get('fast_rate_hz', 30.), options.get('fast_width', 640),
         options.get('fast_limit_side_len', 640), options.get('fast_provider', 'cpu')),
        ('accurate', candidate, options.get('accurate_rate_hz', 4.), options.get('accurate_width', 1280),
         options.get('limit_side_len', 960), options.get('provider', 'cpu')),
    ):
        began = time.monotonic()
        backend = detector_for(model, {**options, 'input_size': [height, width], 'detect_width': pixels_w,
                                       'limit_side_len': side, 'provider': provider, 'threads': 2})
        backend_owner = ExitStack()
        backend_owner.callback(backend.close)
        stack.enter_context(backend_owner)
        pixels = copies[pixels_w] if copies else cv2.resize(warm, (pixels_w, round(height * pixels_w / width)))
        if hasattr(backend, 'detect_quads'):
            backend.detect_quads(pixels)
        else:
            backend.detect(pixels)
        worker = DetectorLane(name, backend, rate, 0 if copies else pixels_w)
        backend_owner.pop_all()
        stack.callback(worker.close)
        lanes[name] = CopyLane(worker, source.copies, pixels_w, [width, height]) if copies else worker
        loading[name] = {'candidate': model, 'rate_hz': rate, 'width': pixels_w,
                         'seconds': time.monotonic() - began, 'metadata': getattr(backend, 'metadata', {})}
    engine = MaskingEngine(lanes, {**options, 'fps': source.fps},
                           renderer=Renderer(style=options.get('style', 'opaque'),
                                             padding=options.get('padding', .3), badge=options.get('badge', False)))
    # drive owns the complete engine lifetime once construction succeeds.
    stack.pop_all()
    return engine, loading


def run_file(input_path, output_path, candidate, options):
    """Retain real encoded media, per-frame masks, packet receipts and health."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    transport_hash, common_hash = transport_fingerprint(), clocked.fingerprint()
    preflight = time.monotonic()
    health = {'preflight': clocked.perf_health()}
    result, failure = {}, None
    try:
        if health['preflight']['pressure_state'] != 'normal' and not options.get('contended', False):
            raise RuntimeError('Reject measurement: preflight memory pressure is ' + health['preflight']['pressure_state'])
        media = clocked.probe_media(input_path)
        window = clocked.source_window(media, options)
        transport = options.get('transport', 'gst')
        if transport == 'gst':
            widths = (options.get('fast_width', 640), options.get('accurate_width', 1280))
            source = GstSource(input_path, media, total_frames=window['total_frames'], detector_widths=widths,
                               decoder=options.get('decoder', 'nvh264dec'), audio=options.get('audio', False),
                               delay_seconds=options.get('delay_seconds', 1.))
            sink = GstSink(output, media['resolution'], media['fps'], encoder=options.get('encoder', 'nvh264enc'),
                           audio=source.audio_enabled, audio_source=source)
            warm, copies = warm_source(source)
        elif transport in ('ffmpeg', 'nut'):
            if options.get('audio'):
                raise ValueError('Common FFmpeg sustained adapter has no audio; use the NUT relay for A/V')
            if transport == 'nut':
                from relay.gst_nut import NutSource, NutSink
                source = NutSource(input_path, media, window['total_frames'], hardware=options.get('decode_hardware', False))
                source.log = output.with_suffix('.nut-decode.log').open('w')
                sink = NutSink(output, media['resolution'], media['fps'], options.get('encoder', 'h264_nvenc'))
            else:
                source = clocked.VideoSource(input_path, media, window['total_frames'], window['total_frames'] / media['fps'])
                sink = clocked.FFmpegSink(output, media['resolution'], media['fps'], options.get('encoder', 'h264_nvenc'))
            source.media = media
            capture = cv2.VideoCapture(str(input_path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
            try:
                ok, warm = capture.read()
                if not ok:
                    raise RuntimeError('No warmup frame')
            finally:
                capture.release()
            copies = {}
        else:
            raise ValueError('Transport must be gst, ffmpeg or nut')
        cv2.setNumThreads(1)
        with ExitStack() as stack:
            engine, loading = engine_for(source, candidate, options, warm, copies, stack)
        health['start'] = clocked.perf_health()
        if health['start']['pressure_state'] != 'normal' and not options.get('contended', False):
            engine.close()
            raise RuntimeError('Reject measurement: START memory pressure is ' + health['start']['pressure_state'])
        sampler = clocked.ResourceSampler()
        try:
            sampler.start()
        except BaseException:
            engine.close()
            raise
        try:
            result = clocked.drive(source, engine, sink)
        finally:
            resources = sampler.finish()
        output_media = clocked.probe_media(output)
        if (output_media['frames'] != result['frames'] or output_media['resolution'] != media['resolution'] or
                abs(output_media['fps'] - media['fps']) > 1e-6):
            raise RuntimeError('Encoded media frame count, resolution or PTS differs from input')
        records = result.pop('records')
        for row in records:
            row.update(mask_shape=list(reversed(media['resolution'])), decoded_at=source.decoded_at.get(row['frame']))
        windows = clocked.measurement_windows(records, source_fps=media['fps'], origin=result['clock_origin'],
                                             ended_at=result['clock_origin'] + result['seconds'],
                                             warmup_frames=window['warmup_frames'])
        result.update(windows)
        result.update({key: value for key, value in windows['steady'].items()
                       if key not in ('frames', 'encoded_frames', 'seconds', 'source_duration_seconds')})
        result.update(resources)
        for stats in result['engine']['lanes'].values():
            stats['actual_hz'] = stats['completed'] / source.duration
            stats['service_quantiles_seconds'] = clocked.quantiles(stats['service_seconds'])
        result.update(warmup_frames=window['warmup_frames'], warmup_seconds=window['warmup_seconds'],
                      steady_frames=window['steady_frames'], steady_duration_seconds=window['steady_seconds'],
                      resolution=media['resolution'], source_media=media, output_media=output_media,
                      source_sha256=clocked.file_sha256(input_path), output_sha256=clocked.file_sha256(output),
                      mask_pixels_sha256=clocked.file_sha256(output.with_suffix('.mask-pixels.zip')),
                      processing_environment=clocked.host_environment(), loading=loading,
                      preflight_and_model_warmup_seconds=time.monotonic() - preflight - result['seconds'],
                      ingest={'queue_drops': source.queue_drops, 'buffer_capacity_frames': source.buffer_capacity_frames},
                      encoder=sink.codec, encoder_command=sink.command,
                      egress_clock='GStreamer parsed H.264 access-unit handoff immediately before mux' if transport == 'gst'
                                   else 'FFmpeg progress mux packet counter upper-bound observation',
                      scope='benchmark-only; Latin-script English/digits; actual video required for privacy credit')
        if transport == 'nut':
            result['nut_decoder'] = {'command': source.command, 'pid': source.process.pid,
                                     'exit': source.process.returncode, **source.runtime}
        if transport == 'gst':
            result['gst_source_descriptions'] = source.descriptions
            result['transport_stages'] = {
                'full_mapped_copy_seconds': clocked.quantiles(source.full_copy_seconds),
                'full_mapped_copy_thread_cpu_seconds': clocked.quantiles(source.full_copy_cpu_seconds),
                'reduced_mapped_copy_seconds': clocked.quantiles(source.reduced_copy_seconds),
                'reduced_mapped_copy_thread_cpu_seconds': clocked.quantiles(source.reduced_copy_cpu_seconds),
                'paired_copy_pull_seconds': clocked.quantiles(source.copy_seconds),
                'sink_write_seconds': clocked.quantiles(sink.write_seconds),
                'sink_write_thread_cpu_seconds': clocked.quantiles(sink.write_cpu_seconds),
                'scope': 'Paired copy pull excludes full-frame map/copy; sink write includes mask ZIP; process CPU includes native GStreamer workers',
            }
            if source.audio_enabled:
                result['audio'] = {'bytes_released': sink.audio_gate.bytes_released,
                                   'last_end_ns': sink.audio_gate.last_end_ns}
        if transport == 'gst':
            for row in records:
                row['transport_source_timestamp'] = source.original_timestamps.get(row['frame'])
        output.with_suffix('.masks.json').write_text(json.dumps(records) + '\n')
        output.with_suffix('.egress.json').write_text(json.dumps(sink.progress) + '\n')
        if common_hash != clocked.fingerprint() or transport_hash != transport_fingerprint():
            raise RuntimeError('Measurement source changed during run')
    except BaseException as error:
        failure = error
        result.update(error=f'{type(error).__name__}: {error}', phase='failed-or-preflight-rejected')
    finally:
        health['end'] = clocked.perf_health()
    result.update(candidate=candidate, options=options, pipeline_sha256=common_hash,
                  transport_sha256=transport_hash, perf_health=health)
    trust = clocked.performance_trust(result)
    result['performance_valid'] = failure is None and trust['valid']
    result['performance_rejection_reasons'] = trust['reasons']
    output.with_suffix('.performance.json').write_text(json.dumps(result, indent=2) + '\n')
    if failure is not None:
        raise failure
    return result
