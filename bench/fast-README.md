# FAST detector experiment

This lane adds FAST Tiny through OnnxTR at the existing `detect_quads` seam.
It does not select a production detector or change the shared factory/engine.
All media produced here are benchmark-only and silent, never demo-ready.

The model, runtime source and license are pinned in `models/manifest.json`.
Additional package licenses are in `bench/fast-licenses.json`. Setup uses
OnnxTR without an ORT extra so Mac keeps CPU/CoreML ORT and Linux keeps the
existing Pascal-compatible CUDA 12/cuDNN 9/ORT 1.20.2 pins. No Torch, account,
paid service or inference network connection is needed.

## Setup after root readiness

The host must have `/tmp/agents/irl-shield/m1-20261029-ready.json` with
`complete:true`. The root's `valid:false` does not waive this lane's own health
checks. All heavy operations hold the shared host lock. Do not start long
untimed setup or quality while that host has timed jobs queued. Timing uses
root's live performance queue, which owns the exclusive lock; queued commands
must never call a launcher that acquires it again.

Linux, from this dedicated worktree (Python 3.11 at `FAST_PYTHON`):

```bash
bench/fast-linux shared bench/fast-setup
```

Mac, with source sync and execution in the same script:

```bash
bench/fast-host shared bench/fast-setup
```

`bench/fast-host` syncs source into `~/code/irl-shield-fast` and excludes `.git`,
`.build`, `out`, `.tmp`, virtual environments and caches. It preserves earlier
lane outputs and does not delete remote files. The Linux launcher uses
`app-t3code-agents.slice`, nice10, and private NVIDIA wheel library directories.
Both launchers cap runtime math/OpenCV threads at two and disable Hub access.

Download explicitly at setup, not inference, into this lane's cache:

```bash
bench/fast-linux shared .tmp/fast/.venv/bin/python models/prepare.py fast-tiny \
  --cache-dir .tmp/fast/models
```

Use `bench/fast-host shared` instead on the Mac. The source-only Mac mirror
still needs its private environment and model setup before quality or timing.

Copy or symlink the existing PP-OCR judge detector and English recognizer files
into this mirror's `models/cache/`; never point a writable cache directory at
another session. Only these two files are needed by the judges:
`ch_PP-OCRv5_det_mobile.onnx` and `en_PP-OCRv5_rec_mobile.onnx`.

## Checks

```bash
.tmp/fast/.venv/bin/python -m unittest bench.fast_test bench.fast_onnx_test -v
.tmp/fast/.venv/bin/python -m unittest discover -s tests -v
.tmp/fast/.venv/bin/python -m unittest discover -s tests/m2 -v
.tmp/fast/.venv/bin/python -m compileall -q bench fixtures models shield relay
swiftc -O Sources/VisionBridge/main.swift -o .build/vision-bridge
```

The final command requires macOS. `fast_onnx_test` uses a tiny synthetic red-label
ONNX graph through the real OnnxTR predictor and CPU EP. It does not load trained
weights or claim OCR quality. The lightweight test suite checks geometry,
provider absence, reference replay, union and interval comparisons.

## Quality

Borrow the complete all7 offline v6-small reference directory read-only. Run
one job at a time on the Mac, which owns Apple Vision and VideoToolbox:

```bash
bench/fast-host shared .tmp/fast/.venv/bin/python -m bench.fast_quality \
  --reference ../irl-shield/out/offline-ppocr-v6-small-a30 \
  --cache-dir .tmp/fast/models --provider coreml --mode alone \
  --encoder h264_videotoolbox --run-id fast-alone-all7
bench/fast-host shared .tmp/fast/.venv/bin/python -m bench.fast_quality \
  --reference ../irl-shield/out/offline-ppocr-v6-small-a30 \
  --cache-dir .tmp/fast/models --provider coreml --mode union \
  --encoder h264_videotoolbox --run-id fast-union-all7
```

FAST alone replaces both lanes (640-square fast, 1024-square accurate by
default); union replays the exact v6 Tiny fast lane and v6 Small accurate lane,
adding FAST to accurate calls. Thus union preserves original v6 coverage and
sampling without paying to rerun its detectors. Static artifacts change only
shape declarations/inferred metadata; their bytes and SHA-256 are retained.

Both modes use the same source videos, D/B/A, rates, widths, padding and motion
options as the reference. Raw input OCR is reused only after checking each
decoded input pixel digest; output pixels go to all three real judges:
Tesseract eng, Apple Vision accurate en-US and PP-OCRv5 English recognizer.
No held-out files are selected. Reference natural and synthetic truth is
rescored with the current unchanged common scorer, including visibility gaps.

Complementarity's denominator is **all v6 leaked natural intervals**, weighted
by intervals rather than frames or boxes. Its numerator requires complete
interval recovery. Partial recovery receives no credit. Guarded recovery also
requires every frame in the interval to remain LIVE with passing real-video
fidelity guards. A protected/slate result cannot earn this credit. The scorecard
keeps raw recovery separately and retains per-interval leak frames for audit.
A globally guard-invalid run remains invalid even if some intervals improve.

These are **ideal/offline quality** experiments. Source-index scheduling does
not establish stream fps, wall-clock latency, CPU budget or Gate 1 eligibility.

## Inference cost

Use the identical natural input video on both hosts. Each provider is explicit;
unavailable providers throw, and actual profiled provider events are required.
CPU operator partitioning under an active CUDA/CoreML provider is recorded.

No new manual timing is permitted. Root's absolute CLI is
`/home/elan/code/irl-shield/scripts/perf-queue` on Linux and
`/Users/elannash/code/irl-shield/scripts/perf-queue` on Mac. Use its
`enqueue <host> <unique-name> --lane fast --priority 2 --cwd <own-mirror>
--receipt '<unique-output>-{attempt}/runtime.json' -- <direct-argv>` interface.
The host label does not SSH; enqueue Mac jobs on the Mac. Do not seal or start
the root runner. `out/fast-queue/jobs.json` records exact direct argv, cwd,
environment and unique retry paths; `out/fast-queue/enqueued-linux.json`
records the four Linux submissions already made. Do not duplicate them.
Mac jobs are intentionally unsubmitted until private setup is ready.

The direct foreground command is the private Python interpreter with
`-m bench.fast_runtime --source <same-source> --cache-dir <own-cache>
--provider <cpu|cuda|coreml> --side <640|1024> --seconds 30
--out <unique-output>-{attempt}`. Preserve the private CUDA library paths and
two-thread environment recorded in `jobs.json`; do not invoke `fast-linux`,
`fast-host`, or `host-lock` inside the queue's exclusive lease. The benchmark
verifies the inherited canonical descriptor and records queue provenance.
Forced-contended execution can produce diagnostics but never valid timing.

Startup, warmup and >=30 seconds
of steady detector calls are separate. Receipts include input/frame SHA-256,
model/derived hashes, runtime/provider options, output quads, p50/p95 wall cost,
process CPU (including native workers), raw ORT profile, and start/end load,
swap and memory-pressure/PSI snapshots. Warn/critical/unknown memory pressure
is rejected; load-per-CPU above one labels the result contended diagnostic.
Accepted timing needs both the raw benchmark's endpoint checks and root's
periodic queue contention evidence. Earlier endpoint-valid receipts are kept
as pre-queue evidence; they do not establish periodic cleanliness. Detector
calls/s is not stream output fps. No stream-performance receipt is claimed by
this experiment.
