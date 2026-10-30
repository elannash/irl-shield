"""Benchmark-only licensed video with generated pulse audio and optical timing."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import time

import av
import numpy as np

from relay.media import Processes, input_nut, output_nut


FPS = 30
SAMPLE_RATE = 48000


def stamp(frame, index, epoch_ms):
    # 48 epoch-millisecond bits then 16 frame-index bits, robust to H.264 loss.
    value = (epoch_ms << 16) | index
    for bit in range(64):
        frame[0:24, bit * 8:(bit + 1) * 8] = 255 if value & (1 << (63 - bit)) else 0
    frame[40:104, 0:64] = 255 if index % FPS < 3 else 0


def read_stamp(frame):
    value = 0
    for bit in range(64):
        value = (value << 1) | int(frame[6:18, bit * 8 + 2:bit * 8 + 6].mean() > 127)
    return value & 65535, value >> 16


def send(fixture, destination, count, events):
    with av.open(fixture) as clip, av.open(destination, "w", format="nut",
                                         options={"flush_packets": "1"}) as output:
        clip.streams.video[0].codec_context.thread_count = 2
        video = output.add_stream("rawvideo", rate=FPS)
        video.width, video.height, video.pix_fmt = 640, 360, "bgr24"
        video.time_base = video.codec_context.time_base = Fraction(1, FPS)
        audio = output.add_stream("pcm_s16le", rate=SAMPLE_RATE)
        audio.layout = "mono"
        audio.time_base = audio.codec_context.time_base = Fraction(1, SAMPLE_RATE)
        frames = iter(clip.decode(video=0))
        origin = time.monotonic()
        for index in range(count):
            try:
                decoded = next(frames)
            except StopIteration:
                clip.seek(0)
                frames = iter(clip.decode(video=0))
                decoded = next(frames)
            pixels = decoded.reformat(width=640, height=360, format="bgr24").to_ndarray()
            remaining = origin + index / FPS - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            epoch_ms = time.time_ns() // 1_000_000
            stamp(pixels, index, epoch_ms)
            frame = av.VideoFrame.from_ndarray(pixels, format="bgr24")
            frame.pts, frame.time_base = index, Fraction(1, FPS)
            for packet in video.encode(frame):
                output.mux(packet)
            sample_start = index * (SAMPLE_RATE // FPS)
            samples = np.arange(sample_start, sample_start + SAMPLE_RATE // FPS)
            tone = np.where(samples % SAMPLE_RATE < SAMPLE_RATE // 10,
                            16000 * np.sin(2 * np.pi * 1000 * samples / SAMPLE_RATE), 0)
            sound = av.AudioFrame.from_ndarray(tone.astype(np.int16).reshape(1, -1),
                                               format="s16", layout="mono")
            sound.sample_rate = SAMPLE_RATE
            sound.pts, sound.time_base = sample_start, Fraction(1, SAMPLE_RATE)
            for packet in audio.encode(sound):
                output.mux(packet)
            events.write(json.dumps({"event": "sent", "index": index, "epoch_ms": epoch_ms,
                                     "pts_seconds": index / FPS}) + "\n")
        for stream in (video, audio):
            for packet in stream.encode():
                output.mux(packet)


def receive(source, events):
    count = audio_samples = 0
    with av.open(source, format="nut", buffer_size=4096,
                 options={"probesize": "32768", "analyzeduration": "1000"}) as incoming:
        for packet in incoming.demux():
            for frame in packet.decode():
                if isinstance(frame, av.VideoFrame):
                    pixels = frame.to_ndarray(format="bgr24")
                    index, epoch_ms = read_stamp(pixels)
                    now_ms = time.time_ns() / 1e6
                    latency = now_ms - epoch_ms
                    if not 0 <= latency < 60000:
                        raise ValueError(f"Invalid optical timestamp at decoded frame {count}")
                    event = {"event": "received", "index": index, "source_epoch_ms": epoch_ms,
                             "received_epoch_ms": now_ms, "latency_ms": latency,
                             "pts_seconds": float(frame.pts * frame.time_base),
                             "flash": bool(pixels[48:96, 8:56].mean() > 127)}
                    if count == 0:
                        print(json.dumps({**event, "event": "first_real_frame"}), flush=True)
                    count += 1
                else:
                    sound = frame.to_ndarray().astype(np.float64).reshape(-1)
                    active = np.flatnonzero(np.abs(sound) > 4000)
                    event = {"event": "audio_received", "pts_seconds": float(frame.pts * frame.time_base),
                             "samples": frame.samples,
                             "first_active_seconds": (float(frame.pts * frame.time_base) +
                                                       int(active[0]) / frame.sample_rate) if active.size else None}
                    audio_samples += frame.samples
                events.write(json.dumps(event) + "\n")
                events.flush()
    if not count or not audio_samples:
        raise RuntimeError(f"Empty sink: {count} video frames, {audio_samples} audio samples")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("send", "receive"))
    parser.add_argument("--url", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--frames", type=int, default=240)
    args = parser.parse_args()
    processes = Processes(args.artifacts)
    try:
        with (args.artifacts / "events.jsonl").open("w") as events:
            if args.role == "send":
                if args.fixture is None:
                    parser.error("send requires --fixture")
                with output_nut(args.url, processes) as destination:
                    send(args.fixture, destination, args.frames, events)
            else:
                with input_nut(args.url, processes, capture=args.artifacts / "capture.mkv") as source:
                    receive(source, events)
    finally:
        processes.finish()
        (args.artifacts / "processes.json").write_text(json.dumps(processes.receipts, indent=2) + "\n")


if __name__ == "__main__":
    main()
