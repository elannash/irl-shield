"""Transport contracts using tiny synthetic CPU frames and owned localhost SRT."""
import unittest
import numpy as np
from ctypes.util import find_library
from pathlib import Path
import shutil
import subprocess
import os
import importlib.util

os.environ.setdefault('GST_REGISTRY', str(Path(__file__).resolve().parents[1] / '.tmp/gst/registry.bin'))

GST_AVAILABLE = bool(find_library('gstreamer-1.0') or Path('/opt/homebrew/lib/libgstreamer-1.0.dylib').exists())
X264_AVAILABLE = bool(shutil.which('gst-inspect-1.0') and subprocess.run(
    ['gst-inspect-1.0', 'x264enc'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0)


@unittest.skipUnless(GST_AVAILABLE, 'Optional GStreamer transport is not installed')
class GstNativeTests(unittest.TestCase):
    def test_padded_bgr_rows_keep_pixels_and_source_timestamps(self):
        from relay.gst_native import Pipeline
        with Pipeline('videotestsrc num-buffers=3 pattern=red ! '
                      'video/x-raw,format=BGR,width=65,height=48,framerate=30/1 ! '
                      'appsink name=frames sync=false') as pipeline:
            samples = [pipeline.pull('frames', 2.) for _ in range(3)]
            self.assertEqual([s.pts_ns for s in samples], [0, 33333333, 66666666])
            for sample in samples:
                self.assertEqual(sample.pixels.shape, (48, 65, 3))
                np.testing.assert_array_equal(sample.pixels[0, 0], [0, 0, 255])
                np.testing.assert_array_equal(sample.pixels[-1, -1], [0, 0, 255])
            self.assertIsNone(pipeline.pull('frames', 2.))
            self.assertTrue(pipeline.eos('frames'))
        self.assertEqual(pipeline.state, 'NULL')


class GstCopyTests(unittest.TestCase):
    def test_scaled_lane_preserves_frame_identity_and_rescales_quads(self):
        from relay.gst import DetectorCopies, CopyLane
        from shield.types import Frame, Detection
        from types import SimpleNamespace
        copies = DetectorCopies(2)
        copies.put(7, (200, 100), {64: np.zeros((32, 64, 3), np.uint8)})
        offered = []
        lane = SimpleNamespace(offer=offered.append,
                               drain=lambda: [Detection('fast', 7, [[[0, 0], [64, 0], [64, 32], [0, 32]]], 3.)],
                               stats={'completed': 1}, close=lambda: None)
        adapter = CopyLane(lane, copies, 64, (200, 100))
        adapter.offer(Frame(7, .7, np.zeros((100, 200, 3), np.uint8)))
        self.assertEqual((offered[0].index, offered[0].pts, offered[0].pixels.shape), (7, .7, (32, 64, 3)))
        receipt = adapter.drain()[0]
        self.assertEqual(receipt.quads, [[[0., 0.], [200., 0.], [200., 100.], [0., 100.]]])
        self.assertEqual((receipt.frame_index, receipt.completed_at), (7, 3.))
        with self.assertRaises(ValueError):
            offered[0].pixels[0, 0, 0] = 255
        with self.assertRaisesRegex(RuntimeError, 'copy'):
            adapter.offer(Frame(8, .8, np.zeros((100, 200, 3), np.uint8)))


@unittest.skipUnless(GST_AVAILABLE, 'Optional GStreamer transport is not installed')
class GstSourceTests(unittest.TestCase):
    def test_source_pairs_scaled_frames_by_pts_and_joins_producer(self):
        from relay.gst import GstSource
        import time
        source = GstSource(None, {'fps': 30., 'frames': 4, 'resolution': [96, 64]},
                           total_frames=4, detector_widths=(48,96),
                           input_chain='videotestsrc num-buffers=4 pattern=red')
        frames = []
        try:
            source.start(time.monotonic())
            deadline = time.monotonic() + 3
            while not source.ended and time.monotonic() < deadline:
                frames.extend(source.poll())
                time.sleep(.002)
            frames.extend(source.poll())
            self.assertEqual([f.index for f in frames], [0, 1, 2, 3])
            self.assertAlmostEqual(frames[-1].pts, .1)
            self.assertEqual(source.copies.get(2, 48).shape, (32, 48, 3))
            self.assertEqual(source.copies.get(2, 96).shape, (64, 96, 3))
            np.testing.assert_array_equal(source.copies.get(2, 48)[-1, -1], [0, 0, 255])
        finally:
            source.close()
        self.assertFalse(source.thread.is_alive())


@unittest.skipUnless(GST_AVAILABLE and X264_AVAILABLE, 'GStreamer GPL x264 CPU test encoder is not installed')
class GstSinkTests(unittest.TestCase):
    def test_encoded_file_contains_presented_pixels_and_one_packet_per_frame(self):
        from relay.gst import GstSink
        from shield.types import PresentedFrame, Coverage
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import cv2
        import zipfile
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'masked.mp4'
            sink = GstSink(output, [96, 64], 30., encoder='x264enc')
            pixels = np.full((64, 96, 3), (0, 0, 255), np.uint8)
            pixels[16:48, 24:72] = 0
            mask = np.zeros((64, 96), np.uint8)
            mask[16:48, 24:72] = 255
            try:
                sink.start()
                for index in range(3):
                    sink.write(PresentedFrame(index, index / 30, pixels, mask, [],
                                              Coverage(0, 0, True, 'covered'), 'LIVE', 0., 0., False, False))
                self.assertEqual(len(sink.finish()), 3)
                self.assertEqual([r['pts_ns'] for r in sink.progress], [0, 33333333, 66666667])
            finally:
                sink.abort()
            with zipfile.ZipFile(output.with_suffix('.mask-pixels.zip')) as archive:
                self.assertEqual(len(archive.namelist()), 3)
            capture = cv2.VideoCapture(str(output))
            try:
                decoded = []
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    decoded.append(frame)
                self.assertEqual(len(decoded), 3)
                self.assertLess(float(decoded[-1][24:40, 32:64].max()), 12.)
                self.assertGreater(float(decoded[-1][0:8, 0:8, 2].mean()), 240.)
            finally:
                capture.release()


class GstAudioTests(unittest.TestCase):
    def test_pcm_waits_for_video_and_splits_at_the_presented_boundary(self):
        from relay.gst import AudioGate
        from relay.gst_native import Sample
        from types import SimpleNamespace
        sent = []
        packets = [Sample(0, 10_000_000, data=np.arange(480, dtype='<i2').tobytes())]
        source = SimpleNamespace(poll_audio=lambda: packets[:] if not sent else [])
        destination = SimpleNamespace(push=lambda *args: sent.append(args))
        gate = AudioGate(destination, source)
        gate.release(5_000_000)
        self.assertEqual([(x[0], len(x[1]), x[2], x[3]) for x in sent], [('audio', 480, 0, 5_000_000)])
        gate.release(10_000_000)
        self.assertEqual([(len(x[1]), x[2], x[3]) for x in sent], [(480, 0, 5_000_000), (480, 5_000_000, 5_000_000)])
        self.assertEqual(b''.join(x[1] for x in sent), packets[0].data)


@unittest.skipUnless(GST_AVAILABLE, 'Optional GStreamer transport is not installed')
class GstFailureTests(unittest.TestCase):
    def test_truncation_and_wrong_cadence_fail_without_replay_or_relabelling(self):
        from relay.gst import GstSource
        import time
        for count, chain, message in (
            (4, 'videotestsrc num-buffers=3 pattern=red', 'truncated'),
            (3, 'videotestsrc num-buffers=3 pattern=red ! video/x-raw,framerate=15/1 ! identity', 'constant-rate'),
        ):
            with self.subTest(message=message):
                source = GstSource(None, {'fps':30.,'frames':count,'resolution':[96,64]}, input_chain=chain)
                try:
                    source.start(time.monotonic())
                    source.thread.join(3)
                    self.assertFalse(source.thread.is_alive())
                    with self.assertRaisesRegex(RuntimeError, message):
                        source.poll()
                finally:
                    source.close()



class GstReadinessTests(unittest.TestCase):
    def test_heavy_command_cannot_take_a_lease_before_root_completes(self):
        from relay import gst_run
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            marker, lock = Path(directory) / 'ready.json', Path(directory) / 'perf.lock'
            with patch.object(gst_run, 'MARKER', marker), patch.object(gst_run, 'LOCK', lock):
                for content in (None, '{"complete": false}'):
                    if content is not None:
                        marker.write_text(content)
                    with self.assertRaisesRegex(RuntimeError, 'has not completed'):
                        with gst_run.host_lease('exclusive'):
                            self.fail('unready heavy command acquired a lease')
                marker.write_text('{"complete": true, "valid": false}')
                with gst_run.host_lease('exclusive') as receipt:
                    self.assertTrue(receipt['complete'])
                    self.assertFalse(receipt['valid'])

    def test_readiness_is_rechecked_after_waiting_for_the_host_lease(self):
        from relay import gst_run
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            marker, lock = Path(directory) / 'ready.json', Path(directory) / 'perf.lock'
            marker.write_text('{"complete": true}')
            def lock_acquired(*args):
                marker.write_text('{"complete": false}')
            with patch.object(gst_run, 'MARKER', marker), patch.object(gst_run, 'LOCK', lock), \
                 patch('fcntl.flock', side_effect=lock_acquired):
                with self.assertRaisesRegex(RuntimeError, 'has not completed'):
                    with gst_run.host_lease('exclusive'):
                        self.fail('revoked readiness was accepted after lease acquisition')

    def test_queued_cli_validates_without_reacquiring_the_external_lock(self):
        from relay import gst_run
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from contextlib import redirect_stderr
        import io
        with TemporaryDirectory() as directory:
            marker=Path(directory)/'ready.json'
            marker.write_text('{"complete":true}')
            lock=Path(directory)/'perf.lock'
            error=io.StringIO()
            with lock.open('w') as lease, patch.object(gst_run,'MARKER',marker), \
                 patch.object(gst_run,'LOCK',lock), patch.dict(os.environ,{
                     'IRL_SHIELD_PERF_QUEUE_FORCED':'0', 'IRL_SHIELD_PERF_QUEUE_ATTEMPT':'1',
                     'IRL_SHIELD_PERF_QUEUE_RECEIPT':str(Path(directory)/'attempt.json'),
                     'IRL_SHIELD_PERF_QUEUE_LEASE_FD':str(lease.fileno())}), \
                 patch('fcntl.flock',side_effect=AssertionError('nested perf lock')), redirect_stderr(error):
                with self.assertRaises(SystemExit) as raised:
                    gst_run.main(['--queued','measure','--source-dir',directory,'--out',directory,
                                  '--steady-seconds','0'])
            self.assertEqual(raised.exception.code,2)
            self.assertIn('at least 30 steady seconds',error.getvalue())

    def test_queue_rejects_a_descriptor_for_another_file(self):
        from relay import gst_run
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            lock=Path(directory)/'perf.lock'
            lock.touch()
            with (Path(directory)/'wrong.lock').open('w') as lease, patch.object(gst_run,'LOCK',lock), \
                 patch.dict(os.environ,{
                     'IRL_SHIELD_PERF_QUEUE_FORCED':'0', 'IRL_SHIELD_PERF_QUEUE_ATTEMPT':'1',
                     'IRL_SHIELD_PERF_QUEUE_RECEIPT':str(Path(directory)/'attempt.json'),
                     'IRL_SHIELD_PERF_QUEUE_LEASE_FD':str(lease.fileno())}):
                with self.assertRaisesRegex(RuntimeError,'canonical performance lock'):
                    gst_run.queue_context()

    def test_forced_queue_marks_the_benchmark_contended_and_retains_context(self):
        from relay import gst_run
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            marker=Path(directory)/'ready.json'
            marker.write_text('{"complete":true}')
            lock=Path(directory)/'perf.lock'
            observed=[]
            def measurement(args):
                observed.append((args.contended,args.queue_context))
                args.out.mkdir()
                return {'control':True}
            with lock.open('w') as lease, patch.object(gst_run,'MARKER',marker), \
                 patch.object(gst_run,'LOCK',lock), patch.dict(os.environ,{
                     'IRL_SHIELD_PERF_QUEUE_FORCED':'1', 'IRL_SHIELD_PERF_QUEUE_ATTEMPT':'2',
                     'IRL_SHIELD_PERF_QUEUE_RECEIPT':str(Path(directory)/'attempt.json'),
                     'IRL_SHIELD_PERF_QUEUE_LEASE_FD':str(lease.fileno())}), \
                 patch('fcntl.flock',side_effect=AssertionError('nested perf lock')), \
                 patch.object(gst_run,'measure',side_effect=measurement):
                gst_run.main(['--queued','measure','--source-dir',directory,'--out',str(Path(directory)/'output')])
            self.assertTrue(observed[0][0])
            self.assertEqual(observed[0][1]['attempt'],2)
            import json
            receipt=json.loads((Path(directory)/'output/queue-context.json').read_text())
            self.assertTrue(receipt['forced'])


@unittest.skipUnless(GST_AVAILABLE and X264_AVAILABLE, 'Optional GStreamer CPU codec test dependencies missing')
class GstPcmIngestTests(unittest.TestCase):
    def test_aac_decode_preserves_audio_pts_for_the_video_gate(self):
        from relay.gst import GstSink, GstSource, AudioGate
        from relay.gst_native import Sample
        from shield.types import PresentedFrame, Coverage
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        import time
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'audio.mp4'
            data = (np.sin(np.arange(9600) * 2 * np.pi / 48) * 12000).astype('<i2').tobytes()
            packets = [Sample(0, 200_000_000, data=data)]
            def audio():
                result = packets[:]
                packets.clear()
                return result
            sink = GstSink(output, [96, 64], 30., encoder='x264enc', audio=True,
                           audio_source=SimpleNamespace(poll_audio=audio))
            try:
                sink.start()
                for index in range(6):
                    sink.write(PresentedFrame(index, index / 30, np.full((64,96,3), 120, np.uint8),
                                              np.zeros((64,96), np.uint8), [], Coverage(0,0,True,'covered'),
                                              'LIVE',0.,0.,False,False))
                sink.finish()
            finally:
                sink.abort()
            source = GstSource(output, {'fps':30., 'frames':6, 'resolution':[96,64]},
                               decoder='avdec_h264', audio=True, total_frames=12)
            try:
                source.start(time.monotonic())
                source.thread.join(4)
                self.assertFalse(source.thread.is_alive())
                self.assertEqual(len(source.poll()), 12)
                audio_samples = source.poll_audio()
                sent = []
                queue = [audio_samples]
                gate = AudioGate(SimpleNamespace(push=lambda *args: sent.append(args)),
                                 SimpleNamespace(poll_audio=lambda: queue.pop() if queue else []))
                gate.release(400_000_000)
                self.assertEqual(sum(len(row[1]) for row in sent), 38400)
                self.assertTrue(audio_samples)
                self.assertEqual(audio_samples[0].pts_ns, 0)
                pcm = np.frombuffer(b''.join(x.data for x in audio_samples), '<i2')
                self.assertGreater(pcm.size, 9000)
                self.assertGreater(int(np.abs(pcm.astype(np.int32)).max()), 8000)
            finally:
                source.close()


@unittest.skipUnless(importlib.util.find_spec('av'), 'Optional PyAV NUT comparison is not installed')
class NutTransportTests(unittest.TestCase):
    def test_nut_adapters_keep_frame_clock_and_encode_only_presented_pixels(self):
        from relay.gst_nut import NutSource, NutSink
        from shield.types import PresentedFrame, Coverage
        from tempfile import TemporaryDirectory
        import cv2
        import time
        with TemporaryDirectory() as directory:
            source_path, output = Path(directory)/'source.mp4', Path(directory)/'masked.mp4'
            pixels = np.full((64,96,3),(0,0,255),np.uint8)
            subprocess.run(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','bgr24',
                            '-s','96x64','-r','30','-i','pipe:0','-an','-c:v','libx264',
                            '-threads','2',str(source_path)], input=pixels.tobytes()*3, check=True)
            source = NutSource(source_path, {'fps':30.,'frames':3,'resolution':[96,64]},6,hardware=False)
            frames = []
            try:
                source.start(time.monotonic())
                source.thread.join(5)
                self.assertFalse(source.thread.is_alive())
                frames = source.poll()
                self.assertEqual([f.index for f in frames], list(range(6)))
                self.assertAlmostEqual(frames[-1].pts, 1/6)
                self.assertEqual(source.process.poll(), 0)
            finally:
                source.close()
            sink = NutSink(output,[96,64],30.,'libx264')
            try:
                sink.start()
                for frame in frames:
                    masked = frame.pixels.copy()
                    masked[16:48,24:72]=0
                    mask = np.zeros((64,96),np.uint8); mask[16:48,24:72]=255
                    sink.write(PresentedFrame(frame.index,frame.pts,masked,mask,[],Coverage(0,0,True,'covered'),
                                              'LIVE',0.,0.,False,False))
                self.assertEqual(len(sink.finish()),6)
            finally:
                sink.abort()
            capture=cv2.VideoCapture(str(output))
            try:
                count=0
                while True:
                    ok, decoded=capture.read()
                    if not ok: break
                    count+=1
                    self.assertLess(int(decoded[24:40,32:64].max()),12)
                    self.assertGreater(float(decoded[:8,:8,2].mean()),240.)
                self.assertEqual(count,6)
            finally:
                capture.release()


@unittest.skipUnless(GST_AVAILABLE and X264_AVAILABLE, 'Optional GStreamer CPU codec dependencies missing')
class GstDiagnosticTests(unittest.TestCase):
    def test_warning_pressure_can_only_produce_an_explicitly_invalid_diagnostic(self):
        from relay.gst_bench import run_file
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            source, output = Path(directory)/'source.mp4', Path(directory)/'output.mp4'
            pixels=np.full((64,96,3),120,np.uint8)
            subprocess.run(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','bgr24','-s','96x64',
                            '-r','30','-i','pipe:0','-an','-c:v','libx264','-threads','2',str(source)],
                           input=pixels.tobytes()*3,check=True)
            options={'transport':'gst','encoder':'x264enc','decoder':'avdec_h264','contended':True,
                     'warmup_seconds':0.,'delay_seconds':.05,'fast_width':48,'accurate_width':96,
                     'fast_rate_hz':30.,'accurate_rate_hz':30.}
            with patch('bench.clocked_pipeline.perf_health',return_value={'pressure_state':'warn'}):
                result=run_file(source,output,'unmasked',options)
            self.assertEqual(result['frames'],3)
            self.assertFalse(result['performance_valid'])
            self.assertIn('contended-diagnostic-trial',result['performance_rejection_reasons'])
            self.assertIn('start-memory-pressure-warn',result['performance_rejection_reasons'])
            self.assertEqual(result['perf_health']['end']['pressure_state'],'warn')


@unittest.skipUnless(GST_AVAILABLE and X264_AVAILABLE, 'Optional GStreamer SRT/CPU codecs missing')
class GstSrtClockTests(unittest.TestCase):
    def test_live_mpegts_quantization_keeps_all_source_frames(self):
        from relay.gst import GstSource
        from relay.gst_native import Pipeline
        import socket
        import time
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as socket_:
            socket_.bind(('127.0.0.1',0))
            port=socket_.getsockname()[1]
        source=GstSource(f'srt://127.0.0.1:{port}?mode=listener',
                         {'fps':30.,'frames':3,'resolution':[96,64]},decoder='avdec_h264')
        sender=Pipeline('videotestsrc num-buffers=3 pattern=red ! '
                        'video/x-raw,format=I420,width=96,height=64,framerate=30/1 ! '
                        'x264enc speed-preset=ultrafast tune=zerolatency threads=2 bframes=0 ! '
                        'h264parse ! mpegtsmux alignment=7 ! '
                        f'srtsink uri="srt://127.0.0.1:{port}?mode=caller" sync=true')
        try:
            source.start(time.monotonic())
            sender.start()
            sender.end([],timeout=5.)
            source.thread.join(5)
            self.assertFalse(source.thread.is_alive(), repr(source.original_timestamps))
            frames=source.poll()
            self.assertEqual([frame.index for frame in frames],[0,1,2])
            self.assertAlmostEqual(frames[-1].pts,2/30)
        finally:
            source.close()
            sender.close()


if __name__ == '__main__':
    unittest.main()
