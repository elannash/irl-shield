# Linux clocked measurements and deferred grading

The same `shield.engine.MaskingEngine`, motion, renderer, frame clock, windows,
mask archives and gate definitions run on both hosts. Providers and encoders
are explicit options. Linux uses the existing pinned CUDA 12/cuDNN 9 environment
in `.tmp/linux-probe/.venv`; `bench/PORTABILITY.md` records runtime limitations
and licenses. No install, download, model export or model rewrite is required.
All footage and images are benchmark-only, without music or audio, and are not
demo-ready assets. Fixture/model attribution remains in
`fixtures/ATTRIBUTION.md` and `models/manifest.json`.

## Host health

START and END retain raw health files or command output, load averages and CPU
count. macOS still requires successful `memory_pressure -Q`, `vm.swapusage` and
the `kern.memorystatus_vm_pressure_level` dispatch flag: 1 normal, 2 warning,
4 critical. An unavailable or unknown flag is never assumed normal.

Linux records `/proc/pressure/{memory,cpu,io}`, `/proc/meminfo`, `/proc/vmstat`,
MemAvailable, swap bytes used, and cumulative swap-in/out page counts. The
primary interfaces are documented by the kernel's
[PSI documentation](https://docs.kernel.org/accounting/psi.html) and
[proc documentation](https://docs.kernel.org/filesystems/proc.html).
Local kernel `include/linux/psi_types.h` also defines SOME as stalled tasks
alongside working tasks, and FULL as stalled tasks with no working tasks.
PSI averages are stall percentages; MemAvailable estimates memory available
for new applications without swapping. Swap already in use is retained as a
receipt and does not alone establish current pressure.

`linux-psi-memavailable-v1` is a **benchmark heuristic**, not a kernel warning
level and not Apple's OS-normal flag. `pressure_level` stays null on Linux.
The heuristic accepts memory health only when memory SOME avg10 is below 1%,
FULL avg10 is below 0.1%, and MemAvailable is at least both 2 GiB and 10% of
MemTotal. It labels the snapshot critical when FULL avg10 is at least 1%, or
MemAvailable is below either 1 GiB or 5%; other complete snapshots are warning.
Missing/malformed required PSI, memory or swap counters remain unknown. CPU
and I/O PSI and load are reported without a speed claim. Endpoint snapshots
can miss brief intermediate pressure; low PSI does not prove an idle host.
The explicit `--contended` mode remains diagnostic and cannot pass performance
trust. These choices preserve the same steady duration, FPS, latency and
protection definitions; they do not equate Linux and macOS pressure sensors.

## Sustained measurement

Run one heavy Linux job at a time. `scripts/linux-bench` sets two-thread native
limits, selects only the existing private NVIDIA libraries, and launches at
nice 10 inside `app-t3code-agents.slice`. CUDA provider arenas remain limited
to 2 GiB each, with heuristic convolution search; this does not cap all device
memory. Dynamic ONNX is the default.

```bash
scripts/linux-bench perf --candidate ppocr-v5-mobile \
  --input out/offline-vision-union-a30/sf-market-natural-input.mp4 \
  --output out/linux-cuda-v5-sustained/output.mp4 \
  --provider cuda --fast-provider cuda --fast-candidate ppocr-v6-tiny \
  --fast-rate-hz 8 --accurate-rate-hz 4 --fast-width 640 --accurate-width 1280 \
  --fast-limit-side-len 640 --limit-side-len 960 \
  --D 1 --before 6 --after 30 --padding .3 \
  --motion-mode phase --motion-width 320 --motion-min-response .05 \
  --encoder h264_nvenc --steady-seconds 30 --warmup-seconds 10
```

The full movie has 1,200 frames at 720p30: 300 startup frames followed by 900
steady frames. Primary encoded added-latency p95, FPS and protection use steady
frames; full movie counts/PTS and startup first-packet delay stay in the receipt.
Exit 2 means the receipt failed validity or a target guard; it does not erase
the measured failure. Source-clock emission delay and coverage remain distinct
from encoded egress latency. A timer alone never establishes 30 FPS.

## Exact-source measurement bundle and Mac grading

The prepared directory supplies input movies and matching `.truth.json` files.
The runner copies their exact bytes into the new bundle, without using fixture
preparation or VideoToolbox. All timing finishes before any judge can be owned.
For a medium/tiny run, changing the accurate candidate is the only detector
change from the v5/tiny trial; both retain 4/8 Hz rates.

```bash
scripts/linux-bench measure --candidate ppocr-v6-medium --split tune \
  --prepared-dir out/offline-vision-union-a30 --defer-score \
  --run-id linux-cuda-medium-tune --seconds 5 --warmup-seconds 10 \
  --provider cuda --fast-provider cuda --fast-candidate ppocr-v6-tiny \
  --fast-rate-hz 8 --accurate-rate-hz 4 --fast-width 640 --accurate-width 1280 \
  --fast-limit-side-len 640 --limit-side-len 960 \
  --D 1 --B 6 --A 30 --padding .3 \
  --motion-mode phase --motion-width 320 --motion-min-response .05 \
  --encoder h264_nvenc --sustained-seconds 30 --sustained-source-clip sf-market
scripts/linux-bench verify \
  --plan out/linux-cuda-medium-tune/measurement-plan.json
```

The exclusive `measurement-plan.json` and its SHA-256 sidecar bind all exact
movies, truth, performance receipts, masks and archives. Verification checks
every artifact, embedded/raw performance agreement, source/output/mask hashes,
candidate/options, and host-neutral source fingerprint before OCR engines are
constructed. The digest excludes the compiled Apple binary; processing/grading
environments retain that binary's hash separately where present. Model/runtime
metadata and provider activation remain in the original performance receipts.
The hash manifest detects accidental changes, not intentional forgery.

After the complete bundle and identical frozen source snapshot reach the Mac,
run with its normal benchmark Python environment:

```bash
python -m bench.cross_host verify \
  --plan out/linux-cuda-medium-tune/measurement-plan.json
python -m bench.cross_host grade \
  --plan out/linux-cuda-medium-tune/measurement-plan.json
```

Grading calls the existing three independent judges on the actual encoded
output's final fixture cycle, outside all performance timing. It uses the same
`score_video` and `aggregate_card` functions as ordinary Mac measurement/scoring.
Original processing host, runtime, options and immutable plan remain retained;
`grading_environment` separately identifies the grader. The final card is not
available until this real grading completes. No empty OCR substitute is used.
All per-clip protection guards stay strictly below 2%, alongside the aggregate
report. Tune measurements cannot claim held-out eligibility. An area ceiling
requires an explicit tune-derived basis and is never invented here.

For the common five-repeat CPU comparison, both hosts use the first 16 pixels
and quads from `out/offline-vision-union-a30/sf-market-natural-input.mp4` and
`sf-market-natural-masked.masks.json`, via existing `bench.cpu_cost`. Thread CPU
measures motion/projection/render; process-tree CPU measures inference. These
CPU medians do not imply wall throughput and omit GPU/device execution time.
