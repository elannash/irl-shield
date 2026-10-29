# IRL Shield measurement contract

Run from Linux with `scripts/mac scripts/bench [options]`. The wrapper synchronizes
source and provisioned assets into the Mac mirror, excludes git/builds/environments/
output, and bounds its process group. `scripts/setup` installs missing free tools,
creates a local Python3.11 environment and compiles the persistent Vision bridge.
`scripts/bench` fetches hash-pinned licensed assets/models, then runs the deadline
engine. It never opens a stream endpoint or uses credentials.

```sh
scripts/mac scripts/setup
scripts/mac --seconds 14400 .venv/bin/python -m bench.offline_quality \
  --candidate ppocr-v6-tiny --split tune --run-id tune-example \
  --provider coreml --fast-provider coreml --static-model
scripts/collect
```

The default split is tune. The real-time bench writes `out/<run-id>/scorecard.json`, copies it
to `out/scorecard.json` and prints a short summary with deltas against
`bench/baseline.json`. Run IDs cannot overwrite previous evidence. Held-out is
reserved for the selected configuration at the milestone hand-back. The committed
baseline is the corrected no-mask control, not an invented detector result.

## Fixtures, scope and truth

The manifest freezes ten independent licensed street clips into seven tune and
three held-out clips. Each is a muted five-second720p30 excerpt. The set includes
US, UK, Slovenian and Mexican streets with Latin-script signage. All media,
including previews and masked outputs, is benchmark-only: visible third-party
brands/logos make it unsuitable for the hackathon demo until separately reviewed.
Sources, authors, licenses and hashes are in `fixtures/ATTRIBUTION.md`, the manifest
and source-page evidence. No music is retained.

Each clip is evaluated naturally and with seeded location-like labels: street,
plate, house and storefront text, varied fonts, rotation/perspective and edge
entry. Exact rendered strings/quads are recorded per frame. Labels become eligible
at30% visible text area and8px height, and are never removed because OCR misses
an input. Three labels follow cumulative median sparse flow of the unmodified
scene at320px; the plate has an independent entry path. This is approximate
camera attachment, not a reconstructed3D scene. The seed is SHA256(clip ID)'s
first four bytes, little-endian. Detector code never receives truth metadata.

Scope is Latin-script text and Arabic digits observed by the judge union:
Tesseract5 `eng --psm11` confidence>=50, Vision accurate `en-US` confidence>=.5,
and PP-OCRv5 English-mobile confidence>=.5. Every detector has independent judges:
PP candidates have Tesseract/Vision; Vision has Tesseract/PP. Models run offline.
Natural input truth requires confidence>=.9 on at least two observed frames per
inferred interval, calibrated before detector selection against no-mask encoding.
Excluded unstable observations remain in evidence. Non-Latin text, single-frame
natural text and text missed by every input judge remain unproven.

The primary unit is string × visible interval, reported separately for natural
text and synthetic labels. Any output judge reading a target or meaningful
fragment in any frame fails that entire interval, including gaps between input
OCR hits. Matching normalizes Unicode alphanumerics: exact short targets, contained
substrings>=3, edit similarity>=.8, or common fragments>=max(3,30% of shorter
string). Geometry requires intersection over the smaller box>.05. Tracks retain
reading aliases, associate spatially and interpolate their geometry across gaps.
Natural visibility before first/after last input reading remains unmeasured.
Known synthetic visibility gaps start separate intervals on re-entry; natural OCR
gaps remain scored continuously. The full tune corpus currently has54 synthetic
visible intervals, with all54 input-positive controls readable.
Known synthetic visibility gaps split intervals even when the same label re-enters;
OCR gaps in natural input remain checked continuously between observations.

Every synthetic interval must be readable by a judge in the input positive
control. A missing input reading fails discrimination; it never shrinks truth.
The corrected no-mask control hides0/61 natural and0/4 synthetic intervals.
A fully masked/slate clip earns zero privacy credit because the real-video guard
fails. Counterexample tests cover OCR gaps, repeated signs, fragments, single
digits, deduplication and denominator shrinkage.

## Quality mode and real-time guards

`bench.offline_quality` blocks for each intended source-index detector sample
and presents on virtual PTS. It uses the same engine, motion geometry, renderer
and independent judges, with ideal detector completion at source PTS. It never
drops input because the host is busy. These cards compare content quality and
explicitly cannot establish real-time coverage, latency, throughput or gate
eligibility. Protected fractions and real-video guards still constrain comparison.
The actual held-out run uses the real frame clock and worker completion times.

The real timed path is paced decode -> independent ingest -> delay engine with
asynchronous latest-frame lanes -> render -> raw pipe -> encoded media. Model
construction/warmup, fixture generation and OCR judging are outside service timing
and reported separately. Rendering uses opaque padded perspective quads by default.
Unknown/stale coverage protects the whole frame, then escalates to slate. HOLD
wins over automatic protection. Missing input keeps the source clock with protected
placeholders. No configured FPS value is substituted for actual encoder delivery.

Evidence includes per-frame coverage ages, state, quads, deadlines, source arrivals,
actual raster-mask hashes/pixels, presentation time and observed encoded completion.
FFmpeg's progress frame counter is its mux `packets_written` counter; sampling and
pipe-reader batching remain in the measured latency upper bound. Output is decoded
again to verify frame count, dimensions, zero-origin CFR PTS and completeness.
CPU is sampled over the process tree (one core=100%); summed RSS may double-count
shared pages. Lane rates, errors, service times, source drops, output clock drift
and deadline misses are retained. Energy and exact GPU/ANE allocation are unmeasured.

Mask area is the actual raster union, median/p95 over ALL frames including full
protection; LIVE-only area is also reported. Every LIVE frame must retain at least
50% outside-mask video, post-encode mean absolute pixel error<12 and standard
deviation>8. A failed LIVE guard zeros that clip's privacy credit. Protected frames
are judged for leaks too and counted separately; they cannot make an all-protected
video pass because a nonempty LIVE set and<2% protection are required.

## Revised gate1

Held-out acceptance requires natural interval hiding>=90%, synthetic100%, a
proposed tune-derived MEDIAN masked-area ceiling, the real-video guard, D<=1s,
steady encoded added latency p95<=1.3s after warmup, sustained720p30 output matching source cadence,
and strictly<2% protected frames on each clip and sustained run. A ceiling requires
both `--area-ceiling` and a receipt in `--area-ceiling-basis`; no default earns a pass.
`--sustained-seconds 30` repeats the slowest measured quality source for900+steady
frames, after the default10s warmup, on a continuous clock. Startup/first-packet
cost, full-run metrics and steady metrics remain separate. A5s quality source
produces450encoded frames and judges only the final150. Original input/truth wrap
through the source; scoring retains original output frame IDs alongside normalized
indices. Repeated pixels establish runtime cost, not more independent
quality examples.1080p performance is reported separately; upscaling does not prove
native1080p recognition. Local file measurements do not establish network latency.

Every perf receipt records raw `memory_pressure -Q`, `sysctl vm.swapusage`,
the OS pressure-level query and load averages before/after the trial. Warn,
critical, unknown or failed queries cannot establish accepted performance.
`--contended` permits a diagnostic run and keeps it invalid. The standalone
receipt command does not perform OCR:

```sh
scripts/mac --seconds 300 .venv/bin/python -m bench.clocked_pipeline \
  --clip sf-market --output out/perf30/sf-market.mp4 \
  --candidate ppocr-v6-tiny --provider coreml --fast-provider coreml --static-model \
  --fast-rate-hz 8 --accurate-rate-hz 4 --after 30 --motion-mode phase \
  --steady-seconds 30 --warmup-seconds 10 --encoder h264_videotoolbox
```

Under host contention, `bench.cpu_cost` records at least five CPU-time repetitions
with pressure/load context. It distinguishes caller thread, parent process and
owned-subprocess CPU. Projection/render cost excludes timeline/control/transport;
the real engine also reports total polling CPU per output, including empty polls.

Useful knobs: `--D`, `--B`, `--A`, `--fast-rate-hz`, `--accurate-rate-hz`, lane
widths, provider, fixed-shape models, padding and motion analysis width. Parameter
changes are tuned on the tune split only and retained/rejected in `bench/LOG.md`.

```sh
scripts/mac scripts/check
scripts/mac .venv/bin/python -m bench.faults
```

The fault probe uses synthetic in-memory video, real detector worker scheduling,
induced lane stalls, input loss and a scene cut during a stall. It asserts that no
uncovered frame leaves in LIVE and no protected output contains the raw input.
TLA+ control-state verification belongs to M2, not this milestone.

`bench.run`, `bench.pipeline`, `bench.reference_engine` and the old `bench.perf`
remain only to reproduce pre-clocked references. Their scorecards are explicitly
ineligible for the revised gate. `vision-scheduled` is a legacy composite and is
rejected by the clocked adapter because it cannot preserve per-lane source ages.

Retrospective `python -m bench.regrade <original-run-id>` supports unrotated
legacy/offline evidence only. It refuses clocked quality windows before writing a
receipt. Clocked truth uses the retained source-frame mapping in `clocked_bench`.
Rescored cards recompute percentage-point deltas against the named current baseline;
missing raw legacy controls remain explicitly unverified and cannot pass calibration.
