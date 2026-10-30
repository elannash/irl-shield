"""Bound one localhost scenario and write a non-vacuous transport receipt."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import numpy as np


def url(protocol, port, listener=False):
    if protocol == "rtmp":
        return f"rtmp://127.0.0.1:{port}/live/m2"
    return f"srt://127.0.0.1:{port}?mode={'listener' if listener else 'caller'}&latency=120&linger=2"


def assert_ports_free(ports, protocol):
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM if protocol == "rtmp" else socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))


def wait_bound(port, protocol, child):
    deadline = time.monotonic() + 10
    while child.poll() is None:
        try:
            assert_ports_free([port], protocol)
        except OSError:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Listener did not bind owned port {port}")
        time.sleep(0.05)
    raise RuntimeError(f"Listener exited before binding port {port}: {child.returncode}")


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def summarize(directory, frames):
    sent = records(directory / "sender/events.jsonl")
    received = records(directory / "sink/events.jsonl")
    videos = [row for row in received if row["event"] == "received"]
    sounds = [row for row in received if row["event"] == "audio_received"]
    indices = [row["index"] for row in videos]
    expected = list(range(frames))
    if [row["index"] for row in sent] != expected or indices != expected:
        raise RuntimeError(f"Frame loss/duplication/reorder: sent={len(sent)}, sink={len(indices)}, expected={frames}")
    flashes = [row["pts_seconds"] for i, row in enumerate(videos)
               if row["flash"] and (i == 0 or not videos[i - 1]["flash"])]
    pulses = []
    for row in sounds:
        active = row["first_active_seconds"]
        if active is not None and (not pulses or active - pulses[-1] > 0.5):
            pulses.append(active)
    if len(flashes) != len(pulses) or len(flashes) < 3:
        raise RuntimeError(f"Pulse evidence missing: flashes={flashes}, audio={pulses}")
    latency = np.array([row["latency_ms"] for row in videos])
    sync_ms = [(audio - video) * 1000 for video, audio in zip(flashes, pulses)]
    return {"video_sent": len(sent), "video_received": len(videos), "indices_exact": True,
            "audio_samples": sum(row["samples"] for row in sounds),
            "latency_ms": {"min": float(latency.min()), "median": float(np.median(latency)),
                           "p95": float(np.percentile(latency, 95)), "max": float(latency.max())},
            "av_sync_audio_minus_flash_ms": sync_ms,
            "flashes_pts_seconds": flashes, "audio_pulses_pts_seconds": pulses,
            "measurement": "Optical source epoch-ms sampled before sender encode to decoded sink wall time; same Mac clock. Includes all codecs, transports and buffering. A/V compares decoded PTS of white-flash onset and generated 1kHz pulse onset above amplitude 4000."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", choices=("rtmp", "srt"), required=True)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=240)
    parser.add_argument("--port", type=int, default=19460)
    parser.add_argument("--deadline", type=float, default=45)
    args = parser.parse_args()
    if not os.environ.get("M2_MAC_WINDOW"):
        parser.error("M2_MAC_WINDOW must name the parent's explicit Mac window; waiting is not permission")
    directory = args.artifacts.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    ports = [args.port] if args.baseline else [args.port, args.port + 1]
    assert_ports_free(ports, args.protocol)
    children = []
    files = []
    exits = []
    started = datetime.now(timezone.utc).isoformat()

    def start(name, command, inherit=False):
        log = (directory / f"{name}.log").open("w")
        files.append(log)
        child = subprocess.Popen([sys.executable, "-m", *command],
                                 stdout=None if inherit else log, stderr=log, start_new_session=True)
        children.append((name, child))
        return child

    def interrupted(number, frame):
        raise SystemExit(128 + number)

    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, interrupted)
    try:
        sink_port = args.port if args.baseline else args.port + 1
        sink = start("sink", ["relay.synthetic", "receive", "--url", url(args.protocol, sink_port, True),
                              "--artifacts", str(directory / "sink")], inherit=True)
        wait_bound(sink_port, args.protocol, sink)
        if not args.baseline:
            relay = start("relay", ["relay.run", "--input", url(args.protocol, args.port, True), "--output",
                                    url(args.protocol, sink_port), "--artifacts", str(directory / "relay")])
            wait_bound(args.port, args.protocol, relay)
        start("sender", ["relay.synthetic", "send", "--url", url(args.protocol, args.port),
                                  "--fixture", str(args.fixture), "--frames", str(args.frames),
                                  "--artifacts", str(directory / "sender")])
        deadline = time.monotonic() + args.deadline
        while any(child.poll() is None for _, child in children):
            failed = [(name, child.returncode) for name, child in children
                      if child.poll() is not None and child.returncode != 0]
            if failed:
                raise RuntimeError(f"Scenario process failed: {failed}; see {directory}")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Scenario exceeded {args.deadline}s; see {directory}")
            time.sleep(0.1)
        failed = [(name, child.returncode) for name, child in children if child.returncode != 0]
        if failed:
            raise RuntimeError(f"Scenario process failed: {failed}; see {directory}")
        receipt = summarize(directory, args.frames)
        receipt.update({"started_utc": started, "protocol": args.protocol, "baseline": args.baseline,
                        "window": os.environ["M2_MAC_WINDOW"], "ports": ports})
        (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2), flush=True)
    finally:
        for name, child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=4)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=3)
            exits.append({"name": name, "pid": child.pid, "exit": child.returncode})
        for log in files:
            log.close()
        (directory / "processes.json").write_text(json.dumps(exits, indent=2) + "\n")
        assert_ports_free(ports, args.protocol)


if __name__ == "__main__":
    main()
