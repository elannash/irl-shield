"""Read captures and process receipts after media scenarios have stopped."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess

import av
import cv2

from relay.scenario import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    report = {"runs": {}, "processes": [], "ports_free": []}
    for directory in sorted(args.directory.iterdir()):
        if not directory.is_dir():
            continue
        item = {}
        for path in directory.rglob("processes.json"):
            for row in json.loads(path.read_text()):
                try:
                    os.kill(row["pid"], 0)
                    alive = True
                except ProcessLookupError:
                    alive = False
                report["processes"].append({"receipt": str(path), **row, "alive": alive})
        capture = directory / "sink/capture.mkv"
        if capture.exists():
            probe = subprocess.run(["ffprobe", "-v", "error", "-threads", "2", "-count_frames",
                                    "-show_streams", "-show_format", "-of", "json", str(capture)],
                                   capture_output=True, text=True, check=True)
            (directory / "probe.json").write_text(probe.stdout)
            item["probe"] = json.loads(probe.stdout)
            item["probe_stderr"] = probe.stderr
            with av.open(capture) as clip:
                frame = next(clip.decode(video=0))
                pixels = frame.to_ndarray(format="bgr24")
                if not cv2.imwrite(str(directory / "benchmark-only-first-frame.png"), pixels):
                    raise RuntimeError("Could not write benchmark evidence frame")
                item["scene_bgr_stddev_below_instrumentation"] = float(pixels[110:].std())
            try:
                item["media"] = summarize(directory, 240)
            except RuntimeError as error:
                item["media_error"] = str(error)
        report["runs"][directory.name] = item
    for protocol, kind in (("tcp", socket.SOCK_STREAM), ("udp", socket.SOCK_DGRAM)):
        for port in (19460, 19461):
            with socket.socket(socket.AF_INET, kind) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))
            report["ports_free"].append({"protocol": protocol, "port": port})
    if any(row["alive"] for row in report["processes"]):
        raise RuntimeError("An owned process PID still exists; inspect report before releasing window")
    (args.directory / "inspection.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"runs": list(report["runs"]), "processes_confirmed_exited": len(report["processes"]),
                      "ports_free": report["ports_free"]}, indent=2))


if __name__ == "__main__":
    main()
