"""Run one local input → MaskingEngine → output connection."""
import argparse
import json
import math
from pathlib import Path

from relay.bridge import NoOpDetector, bridge_nut
from relay.media import Processes, input_nut, output_nut
from shield.engine import MaskingEngine
from shield.lanes import DetectorLane


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=.1)
    parser.add_argument("--fps", type=float, default=30)
    args = parser.parse_args()
    if (not math.isfinite(args.delay_seconds) or args.delay_seconds <= 0 or
            not math.isfinite(args.fps) or args.fps <= 0):
        parser.error('A positive finite delay and source frame rate are required')
    processes = Processes(args.artifacts)
    try:
        with (args.artifacts / "engine.jsonl").open("w") as events:
            with output_nut(args.output, processes) as destination:
                with input_nut(args.input, processes) as source:
                    lanes = {name: DetectorLane(name, NoOpDetector(), args.fps)
                             for name in ('fast', 'accurate')}
                    engine = MaskingEngine(lanes, {'delay_seconds': args.delay_seconds, 'fps': args.fps})
                    bridge_nut(source, destination, engine, events)
    finally:
        processes.finish()
        (args.artifacts / "processes.json").write_text(json.dumps(processes.receipts, indent=2) + "\n")


if __name__ == "__main__":
    main()
