"""FFmpeg and libsrt process plumbing. No service or global configuration."""
from contextlib import contextmanager
import ipaddress
from pathlib import Path
import subprocess
from urllib.parse import urlsplit


def local_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in {"rtmp", "srt"} or parsed.username or parsed.password:
        raise ValueError("Use a credential-free RTMP or SRT URL")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as error:
        raise ValueError("Use a literal loopback or Tailscale IP address") from error
    if not (address.is_loopback or address in ipaddress.ip_network("100.64.0.0/10")):
        raise ValueError("Only loopback and Tailscale addresses are allowed")
    if parsed.port is None:
        raise ValueError("An explicit owned port is required")
    return parsed.scheme


class Processes:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.children = []
        self.logs = []
        self.receipts = []

    def start(self, name, command, **kwargs):
        log = (self.directory / f"{name}.log").open("wb")
        self.logs.append(log)
        process = subprocess.Popen(command, stderr=log, **kwargs)
        self.children.append((name, process))
        return process

    def finish(self):
        for name, process in reversed(self.children):
            if process.poll() is None:
                process.terminate()
            try:
                code = process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait(timeout=3)
            self.receipts.append({"name": name, "pid": process.pid, "exit": code})
        for log in self.logs:
            log.close()


@contextmanager
def input_nut(url, processes, ffmpeg="ffmpeg", srt="srt-live-transmit", capture=None):
    protocol = local_url(url)
    common = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "warning", "-y",
              "-filter_threads", "2", "-filter_complex_threads", "2", "-threads", "2",
              "-probesize", "32768", "-analyzeduration", "100000"]
    upstream = None
    if protocol == "srt":
        upstream = processes.start("srt-input", [srt, "-autoreconnect:no", "-buffering:1", "-chunk:1316",
                                                 url, "file://con"], stdout=subprocess.PIPE)
        common += ["-f", "mpegts", "-i", "pipe:0"]
    else:
        common += ["-listen", "1", "-i", url]
    if capture:
        common += ["-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", str(capture)]
    common += ["-map", "0:v:0", "-map", "0:a:0?", "-c:v", "rawvideo",
               "-pix_fmt", "bgr24", "-threads:v", "1", "-fps_mode", "passthrough",
               "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", "-f", "nut", "pipe:1"]
    decoder = processes.start("decode", common, stdin=upstream.stdout if upstream else subprocess.DEVNULL,
                              stdout=subprocess.PIPE)
    if upstream:
        upstream.stdout.close()
    try:
        yield decoder.stdout
        decoder.stdout.close()
        code = decoder.wait(timeout=10)
        if code:
            raise RuntimeError(f"Input FFmpeg exited {code}; see {processes.directory}/decode.log")
    finally:
        decoder.stdout.close()


@contextmanager
def output_nut(url, processes, ffmpeg="ffmpeg", srt="srt-live-transmit"):
    protocol = local_url(url)
    downstream = None
    if protocol == "srt":
        downstream = processes.start("srt-output", [srt, "-autoreconnect:no", "-buffering:1", "-chunk:1316",
                                                    "file://con", url],
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
    command = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "warning", "-y",
               "-filter_threads", "2", "-filter_complex_threads", "2", "-threads", "2",
               "-probesize", "32768", "-analyzeduration", "1000",
               "-f", "nut", "-i", "pipe:0", "-map", "0:v:0", "-map", "0:a:0?",
               "-c:v", "h264_videotoolbox", "-realtime", "1", "-allow_sw", "0",
               "-b:v", "2000000", "-g", "30", "-bf", "0", "-pix_fmt", "yuv420p",
               "-fps_mode", "passthrough", "-c:a", "aac", "-b:a", "128000",
               "-flush_packets", "1"]
    if protocol == "srt":
        command += ["-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "pipe:1"]
    else:
        command += ["-f", "flv", url]
    encoder = processes.start("encode", command, stdin=subprocess.PIPE,
                              stdout=downstream.stdin if downstream else subprocess.DEVNULL)
    if downstream:
        downstream.stdin.close()
    try:
        yield encoder.stdin
        encoder.stdin.close()
        code = encoder.wait(timeout=15)
        if code:
            raise RuntimeError(f"Output FFmpeg exited {code}; see {processes.directory}/encode.log")
        if downstream:
            # This sample utility stays open after stdin EOF. A bounded local
            # drain then SIGTERM lets its own SRT shutdown/linger finish.
            try:
                downstream.wait(timeout=1)
            except subprocess.TimeoutExpired:
                downstream.terminate()
                downstream.wait(timeout=3)
            if downstream.returncode != 0:
                raise RuntimeError(f"SRT output exited {downstream.returncode}")
    finally:
        if not encoder.stdin.closed:
            encoder.stdin.close()
