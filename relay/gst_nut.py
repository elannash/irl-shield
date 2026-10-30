"""FFmpeg/NUT/PyAV comparison at the existing finite clocked transport seam.

PyAV 16.0.1 is BSD-3-Clause; actual FFmpeg library/build licensing is retained
in the runtime receipt. Audio remains a separate received A/V control.
"""
from fractions import Fraction
import queue
import subprocess
import time

import av
from av._core import library_meta
import numpy as np

from bench.clocked_pipeline import VideoSource, FFmpegSink
from shield.types import Frame


class NutSource(VideoSource):
    def __init__(self, path, media, total_frames, *, hardware=True):
        super().__init__(path, media, max_frames=total_frames,
                         repeat_seconds=total_frames / media['fps'])
        self.runtime = {'pyav_version': av.__version__, 'ffmpeg_libraries': library_meta}
        self.process = None
        self.log = None
        self.hardware = hardware
        self.command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                        '-threads', '2', '-filter_threads', '2', '-stream_loop', '-1']
        if hardware:
            self.command += ['-hwaccel', 'cuda']
        self.command += ['-i', str(path), '-map', '0:v:0', '-an', '-c:v', 'rawvideo',
                         '-pix_fmt', 'bgr24', '-threads:v', '1', '-fps_mode', 'passthrough',
                         '-frames:v', str(total_frames), '-f', 'nut', 'pipe:1']

    def _produce(self):
        try:
            self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE,
                                            stderr=self.log, stdin=subprocess.DEVNULL)
            with av.open(self.process.stdout, format='nut', buffer_size=4096) as incoming:
                for index, decoded in enumerate(incoming.decode(video=0)):
                    pts = index / self.fps
                    if decoded.pts is None or abs(float(decoded.pts * decoded.time_base) - pts) > 1e-5:
                        raise RuntimeError('NUT decode source PTS differs from original frame clock')
                    if self.stop.wait(max(0., self.origin + pts - time.monotonic())):
                        return
                    self.arrivals[index] = time.monotonic()
                    pixels = decoded.to_ndarray(format='bgr24')
                    self.decoded_at[index] = time.monotonic()
                    try:
                        self.frames.put_nowait(Frame(index, pts, pixels))
                    except queue.Full:
                        try:
                            dropped = self.frames.get_nowait()
                            self.queue_drops.append(dropped.index)
                        except queue.Empty:
                            pass
                        self.frames.put_nowait(Frame(index, pts, pixels))
            if self.process.wait(timeout=10):
                raise RuntimeError('NUT decode FFmpeg failed')
        except Exception as error:
            if not self.stop.is_set():
                self.error = error
        finally:
            self._stop_process()
            self.finished.set()

    def _stop_process(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.process.stdout and not self.process.stdout.closed:
            self.process.stdout.close()

    def close(self):
        self.stop.set()
        try:
            self._stop_process()
            super().close()
        finally:
            if self.log is not None:
                self.log.close()


class NutSink(FFmpegSink):
    def __init__(self, path, resolution, fps, codec):
        super().__init__(path, resolution, fps, codec)
        start, end = self.command.index('-f'), self.command.index('-an')
        self.command[start:end] = ['-f', 'nut', '-i', 'pipe:0']
        self.container = self.stream = None
        self.submitted = 0

    def start(self):
        super().start()
        self.container = av.open(self.process.stdin, 'w', format='nut', buffer_size=4096,
                                 options={'flush_packets':'1','max_interleave_delta':'0'})
        self.stream = self.container.add_stream('rawvideo', rate=Fraction(str(self.fps)))
        self.stream.width, self.stream.height = self.resolution
        self.stream.pix_fmt = 'bgr24'
        self.stream.time_base = self.stream.codec_context.time_base = Fraction(1, 90000)

    def write(self, frame):
        height, width = frame.pixels.shape[:2]
        if [width,height] != self.resolution or frame.mask.shape != (height,width) or frame.index != self.submitted:
            raise ValueError('NUT presented shape or index changed')
        video = av.VideoFrame.from_ndarray(frame.pixels, format='bgr24')
        video.pts, video.time_base = round(frame.pts * 90000), Fraction(1,90000)
        for packet in self.stream.encode(video):
            self.container.mux(packet)
        self.masks.writestr(f'{frame.index:08d}.bin', np.packbits(frame.mask>0,bitorder='little').tobytes())
        self.submitted += 1

    def finish(self):
        for packet in self.stream.encode():
            self.container.mux(packet)
        self.container.close()
        self.container = None
        return super().finish()

    def abort(self):
        # Stop the child first so a failing mux flush cannot block on a full pipe.
        super().abort()
        if self.container is not None:
            try:
                self.container.close()
            except (BrokenPipeError, ValueError):
                pass
            self.container = None
