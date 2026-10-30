# GStreamer lane ledger

Append-only lane events; no held-out data. All street-video artifacts are
benchmark-only, not demo-ready. The source snapshot and raw receipts take
precedence over a prose summary.

## 2026-10-29 — implementation start

- Task started approximately 23:49 UTC; four-hour stop is approximately 03:49
  UTC on October 30. Assigned and verified HEAD:
  `2dd52a610eb569ac51eedc84b7840fa852da96c9`.
- Worktree `/home/elan/.t3/worktrees/irl-shield/t3-ae5d7088` was clean. Renamed
  app branch `t3/gstreamer-transport` in place to `elannash/m1-gst`.
- No commits, pushes, PRs, merges, subagents, Twitch sends or public endpoints.
- Engine/common benchmark fingerprint verified:
  `17ec5477dc6f6f02d6c2370cc4e4e8726de2fe91eea1a244b9977a18b8a40b18`.
- Loaded codebase-design, TDD and the test gate before implementation/tests;
  read routing/machine/architecture/bench contracts. Tests observe the actual
  transport adapter interfaces. Existing engine tests own engine privacy rules.

## 2026-10-29 23:58–00:00 UTC — synthetic checks before readiness

- Linux root readiness marker absent. No lane inference, heavy install,
  real-video benchmark, sustained timing or GPU encode/decode started.
- Private Linux venv `.tmp/gst/.venv` uses Python 3.11.14, with read-only `.pth`
  references to the existing Linux GPU/model/M2 runtimes. No package install or
  shared-env edit. Loaded NumPy 2.2.6, OpenCV 4.11.0, psutil 7.0.0.
- GStreamer system version is 1.28.2. System PyGObject targets Python 3.14;
  ctypes + installed typelibs avoid changing the detector's Python ABI.
- New synthetic tests progressed red→green for native row-stride/timestamps,
  scaled-copy mapping, paced source, encoded presented pixels and audio gating.
  A truncated-cycle regression failed behaviorally before its fix (replayed
  input hid EOF), then passed after explicit cycle-length validation.
- Raw red receipts:
  `/tmp/agents/irl-shield/gst/red-{native,copy,source,sink,audio,truncated}.log`.
- Linux first broad unit run: 78 tests, one existing Mac-only skip, pass.
  `/tmp/agents/irl-shield/gst/linux-tests.log`.
- First M2 test attempt lacked PyAV; corrected only this lane's `.pth` reference
  to the existing `.../.tmp/m2/linux-venv`. M2: three tests passed, no installs.
  `/tmp/agents/irl-shield/gst/linux-m2-tests.log`.
- Seven lane tests pass, including readiness refusal and `complete:true` with
  root `valid:false`. The actual CLI refused before root completion:
  `RuntimeError: Root sustained receipt has not completed: /tmp/agents/irl-shield/m1-20261029-ready.json`.
  `/tmp/agents/irl-shield/gst/readiness-denial.log`.
- Own Mac mirror created at `/Users/elannash/code/irl-shield-gst`. Private venv
  references the existing Mac Python 3.11 runtime read-only (NumPy 2.2.6,
  OpenCV 4.11.0, PyAV 16.0.1). No Mac GStreamer installation before readiness.

Measurement verdict pending: no sustained fps/p95, guarded quality score, CPU
comparison or A/V result exists yet. The common sealed-measurement command and
exact deferred grading path are documented in `docs/GSTREAMER.md`.

## 2026-10-30 00:02 UTC — pre-readiness protocol incident

The Mac broad unit run completed 79 tests, four optional-GStreamer skips.
Its existing `tests/test_pipeline.py` invokes VideoToolbox on a 12-frame
synthetic clip (and three tiny delayed re-encodes). This was started before the
root marker, contrary to the CPU-only pre-readiness instruction. It is a lane
verification mistake, not an accepted timing/performance receipt. The process
finished; no foreign process was stopped or altered. Its log is
`/tmp/agents/irl-shield/gst/mac-tests-before-gst.log` on the Mac. No further Mac
codec or full-gate execution will occur before root readiness. This entry
corrects the earlier statement that no lane GPU work had started.

## 2026-10-30 — host-lock clarification applied

Untimed heavy setup (brew/pip, model export/download, media preparation, quality)
uses SH on the same perf.lock. Timed work uses EX. Root may retain EX after its
first marker through further host comparisons. Updated `mac-install` to SH;
marker completion only permits a blocking lease attempt. No new work was
started on the strength of a marker alone.

## 2026-10-30 00:03 UTC — root marker correction

Linux briefly published `complete:true,valid:false` for a preflight rejection,
then the conductor revoked it to `complete:false`. The only legitimately
started lane command was `inspect` waiting for SH; no timed inference or Linux
performance baseline started. A new regression reproduced accepting revoked
readiness after lock acquisition; `host_lease` now checks the marker again
inside the acquired lease. Red receipt:
`/tmp/agents/irl-shield/gst/red-marker-revoked.log`; nine lane tests pass after
repair. Root jobs and lock were not stopped or altered. Mac marker unaffected.

## 2026-10-30 — repeated AAC regression

The tiny CPU codec test caught AAC padding from one file cycle overlapping the
next cycle. `AudioGate` correctly refused overlapping PCM. Source PCM now clips
to each cycle's exact video interval before enqueue; audio before the first
video PTS waits for that anchor. Two 0.2s synthetic cycles release exactly
38,400 S16LE bytes (19,200 samples) with no overlap. Behavioral red receipt:
`/tmp/agents/irl-shield/gst/red-audio-repeat.log`; nine lane tests pass after fix.

## 2026-10-30 00:07 UTC — license receipts

Installed Linux `gst-inspect` reports core plugins/nvcodec/libav LGPL and x264
GPL, version 1.28.2. Copied installed copyright metadata read-only to lane
`.tmp/gst/licenses/`. It records LGPL-2.0-or-later plus selected LGPL-2.1-or-later
GStreamer files; GIRepository runtime LGPL-2.0-or-later, embedded cmph LGPL-2.0
or MPL-1.1, and separate scanner/tool GPL files. Documentation now distinguishes
those actual file-level notices instead of assigning a uniform version to the
whole package. Nothing is redistributed or installed by this metadata read.

## 2026-10-30 00:22–00:24 UTC — rejection, third adapter, measurement queued

- Legitimately queued Linux A/V command acquired EX, then rejected before any
  media generation/inference because pressure was non-normal. It exited1 and
  retained `/tmp/agents/irl-shield/gst/av-linux.log`. This initial A/V rejection
  recorded the reason but not raw health (unfinished evidence for that attempt).
  Future A/V preflight writes the exact raw health before refusing.
- The source snapshot for that atomic operation is retained under
  `.tmp/gst/source-av/` with a transport hash. No timing from it is credited.
- Added a real FFmpeg/NUT/PyAV source/sink comparison (`--transport nut`),
  default CPU decode matching the existing relay, using the identical common
  clocked drive/windows/score schema. Tiny real-codec TDD went red on missing
  adapter then green: three source frames repeated into six, PTS preserved,
  only presented masked pixels encoded. Raw red: `red-nut.log`; ten lane tests
  pass in `lane-tests.log` under `/tmp/agents/irl-shield/gst/`.
- Removed redundant full-width detector branch: reuse the already-owned source
  pixels for that width, resize smaller copies in GStreamer. No engine edits.
- Set per-lane GStreamer registry/cache paths and scoped CUDA wheel library
  paths. Added a Python SIGALRM unwind so deadline exceptions close owned
  adapters rather than abandoning FFmpeg children. No host runtime was changed.
- 00:23:00 UTC lightweight Linux health sample: normal pressure, 1/5/15 load
  11.9033/18.5332/15.2983, swap7,568,068,608 bytes, available7,013,048,320 bytes.
  Raw `/tmp/agents/irl-shield/gst/current-health.json`. Load is not assumed quiet
  from a normal memory classification; each timed receipt keeps raw START/END.
- Queued `relay/gst_linux measure --source-dir
  /home/elan/code/irl-shield/out/offline-ppocr-v5-mobile-a30 --out
  out/gst-linux-tune --candidate ppocr-v6-small --transport gst --options
  .tmp/gst/options-gst.json` under EX. All seven tune clips, both variants,
  10s warmup, separate30s steady; no held-out data. Log:
  `/tmp/agents/irl-shield/gst/measure-gst-linux.log`.

## 2026-10-30 00:23–00:28 UTC — first real output and diagnostic-only continuation

The first SF Market natural variant completed450/450 encoded720p30 frames,
300warmup+150short steady. Observed short-steady rate30.05067fps, encoded added
latency p50/p95 1.16935/1.18046s,0% protection, CPU159.8179% (one core=100%).
START normal, END warn, so performance invalid (also only5s steady). No privacy
score or accepted30s throughput claim. Raw:
`out/gst-linux-tune/sf-market-natural-masked.performance.json`, `.masks.json`,
`.mask-pixels.zip`, `.mp4`, `.egress.json`. Exact transport source retained in
`.tmp/gst/source-gst-first/`. The next synthetic variant refused at preflight
warn and the command exited1. No passing scorecard was fabricated.

Copy/submit p95 in that short diagnostic: full mapped copy1.5765ms, reduced
mapped copy0.4919ms, sink write3.7191ms (includes mask ZIP); process CPU includes
native worker threads. These do not establish that GPU retained-frame rendering
would dominate the remaining budget; no zero-copy stretch is started.

A tiny CPU diagnostic test then exposed forced-framerate caps linking failure.
Decoder accepts the High4:4:4 input, but qtdemux advertised20fps for a3-frame
file whose actual decoded PTS are30fps. Independent gst-launch probes isolated
rate caps (size-only and bare decoder pass; rate-only fails). Source now lets
advisory framerate caps negotiate and still strictly validates every actual
source PTS. Raw debug: `/tmp/agents/irl-shield/gst/{warm-debug,diagnostic-debug}.log`.
Eleven lane tests pass, including real diagnostic output under simulated warn
pressure with unconditional `performance_valid:false` and contended reasons.

`contended:true` now follows the existing common bench convention: collect a
labelled diagnostic, never a valid performance receipt. The all-seven tune
bundle was queued with explicit contended options, preserving complete media
for independent quality/deferred scoring. It cannot qualify a transport switch
regardless of its speed. Log:
`/tmp/agents/irl-shield/gst/measure-gst-linux-diagnostic.log`;
output `out/gst-linux-tune-diagnostic`. Source/model/lane policy unchanged from
root's static Small/Tiny8/4Hz configuration, D1s, after30, phase response.05.

## 2026-10-30 00:39–01:20 UTC — completed diagnostic bundles and A/V

Two complete tune-only bundles retain all seven clips, natural and synthetic
variants, plus separate 1200-frame runs (300 warmup, 900 steady). Both plans
were sealed and hash-verified with unchanged common engine fingerprint
`17ec5477dc6f6f02d6c2370cc4e4e8726de2fe91eea1a244b9977a18b8a40b18`.
All 14 prepared source hashes, model hashes and transport snapshots match
between the pair; `/tmp/agents/irl-shield/gst/paired-source-audit.json` records
that audit. These are diagnostic observations, not accepted performance:

| Transport | Steady observed fps | Added latency p95 | Protected | Process CPU (100%=one core) | Peak tree RSS | START → END |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| GStreamer NVDEC/NVENC | 30.058420 | 1.229639 s | 0% | 170.978% | 2352.688 MiB | warn → critical |
| Existing FFmpeg adapter | 30.063906 | 1.191968 s | 0% | 166.552% | 944.055 MiB | normal → warn |

Both explicitly set `contended:true` and `performance_valid:false`. Full raw
load, swap and Linux PSI are in each per-file `.performance.json`, including
separate startup and steady windows. At GStreamer sustained START/END, load1
was 7.013/8.459, swap 8,283,914,240/8,883,318,784 bytes; FFmpeg load1 was
9.131/9.241, swap 8,454,467,584/8,173,133,824 bytes. No causal claim follows
from this pair. Privacy scores and guarded real-video quality remain UNGRADED.
Neither 0% protection nor encoded frames proves readable-text removal.

Raw bundles: `out/gst-linux-tune-diagnostic/measurement-plan.json` and
`out/gst-ffmpeg-linux-tune-diagnostic/measurement-plan.json`. Readable extracts:
`/tmp/agents/irl-shield/gst/{gst,ffmpeg}-diagnostic-summary.json`. Exact then-run
source/options/package/driver receipts are in `.tmp/gst/source-gst-diagnostic/`.
Later SRT, copy immutability and queue-entry changes do not rewrite these runs.

The file control `out/gst-linux-av-v2/av-receipt.json` independently found both
flashes and both beeps in 120 encoded frames. Source audio lagged video by
21 ms, output by 42 ms, so introduced audio lag was 21 ms. Protection was
1.6667%; released mono48kHz PCM was 384,000 bytes. Preflight/START/END pressure
was normal. This four-second unmasked control is neither privacy nor sustained
performance evidence. The generated fixture is authored CC0, seeded texture,
white flashes and sine beeps, with no text/logos/music. A previous A/V attempt
refused before generation under warn pressure; its missing raw preflight was
not reconstructed. Future refusals retain `av-preflight.json`.

The full720p localhost SRT attempt in `out/gst-linux-srt-v5/` decoded 120
source timestamps but FAILED event accounting: zero received flashes and two
beeps. No accepted network receipt exists. Earlier native helper teardown
freed its bus while its publisher was blocked (exit134); publisher lifetime
was corrected by joining before bus close, and that process exited. Source
clock checks exposed one90kHz tick then PCR skew around70us. SRT now ignores
PCR scheduling, retains actual PTS, tolerates only the protocol timestamp
quantum and sends finite-source EOS to drain decoder-held tail frames. A tiny
real localhost regression passes; it does not establish full720p A/V success.
The next queued network control paces elementary streams before TS mux; its
full result is still pending. No RTMP end-to-end or GPU retained-frame claim.

No new SDK/model/dataset was downloaded or installed by this lane. The Linux
owner-installed GStreamer1.28.2 plugins and existing private Python3.11.14
packages are recorded in `out/gst-linux-runtime/gst-runtime.json`,
`.tmp/gst/licenses/`, `.tmp/gst/pyav-libraries.json`, and
`.tmp/gst/ffmpeg-license.txt`. PyAV16.0.1 is BSD-3-Clause; its actual FFmpeg
library metadata says LGPLv3+ but also records x264/x265 build dependencies.
The separate CLI FFmpeg build reports GPL. These are not labelled a uniformly
LGPL-only binary distribution. Models remain existing pinned Apache2 weights.

Protocol incident: an early Mac broad unit suite inadvertently included the
existing12-frame VideoToolbox test before root readiness. It finished; the
owner was informed, no performance credit is claimed, and it was not repeated.
The lane's four pure CPU Mac checks passed separately. GStreamer remains
uninstalled on Mac. The prepared tune media and CC0 control are not staged.

## 2026-10-30 01:35–01:42 UTC — validation and root queue handoff

Linux checks completed in one `bash -e` run: main suite85 passed with one
existing Mac-only skip, M2 suite3 passed, compileall passed. Raw command/output
is `/tmp/agents/irl-shield/gst/linux-final-checks.log`. The full repository gate
also builds the Swift Vision bridge on Mac; that part remains unrun here.
Thirteen transport checks passed, including real CPU pixel/mask/stride output,
copy coordinates/immutability, bounded PCM release/repeat clipping, truncated
or wrong-rate ingest rejection, tiny localhost SRT and actual NUT/PyAV output.
After root supplied the live queue contract, five readiness/queue checks passed
in `/tmp/agents/irl-shield/gst/queue-green.log`. New tests first failed for
missing inherited lease validation and absent forced-context propagation.
The implementation now validates the canonical lock descriptor, preserves
attempt context, and forces contended mode from the injected FORCED flag.
There is no second flock. Linux jobs inherit the runner's T3 slice and process
group; the wrapper refuses another slice rather than creating an escaping scope.

No new manual timing or long untimed setup/quality started after the queue
steer. Five Linux priority2 jobs were submitted to the absolute root CLI;
priority1 root jobs remain first. Outputs refuse overwrites and use unique
`{attempt}` paths. Exact submitted argv/results are in
`.tmp/gst/queue-submissions.json`; source/options are frozen for execution.

| Job | Queue ID | Main expected receipt under this worktree |
| --- | --- | --- |
| GStreamer | `7b22173a250345feabda70f634d3e727` | `out/gst-queued-linux-gst-{attempt}/measurement-plan.json` |
| FFmpeg | `0ef015c1b73b43c286d3ae17feaa9cb4` | `out/gst-queued-linux-ffmpeg-{attempt}/measurement-plan.json` |
| NUT/PyAV | `707989e5b6374199a79d7e155587a67c` | `out/gst-queued-linux-nut-{attempt}/measurement-plan.json` |
| File A/V | `ba0d5517ef214da783d1db214c369642` | `out/gst-queued-linux-av-{attempt}/av-receipt.json` |
| Localhost SRT | `64f65ecfaca747c581623f07e39531d1` | `out/gst-queued-linux-network-{attempt}/network-receipt.json` |

All also retain `queue-context.json`; measurement jobs retain the plan SHA and
`sustained-masked.performance.json`. Root queue attempt/stdout/health receipts
live in `/home/elan/code/irl-shield/.tmp/perf-queue/linux/jobs/<ID>/`.
Neither queue was sealed. No Mac jobs were enqueued: GStreamer setup, fourteen
exact prepared input/truth pairs and the control must be staged first, and
new long SH setup cannot start while root timing is queued there. The five
Mac direct job specifications remain in `relay/gst_queue_jobs.json` for later.

Current transport source SHA is
`b501605e24e458a2b25e9049f952341581b33165f419ce472aa280728b915c06`.
Branch `elannash/m1-gst`, HEAD `2dd52a610eb569ac51eedc84b7840fa852da96c9`;
all changes remain uncommitted for Opus. No engine/render/common bench edits,
no push/PR/merge, no secret or external stream, no other-session job touched.

## 2026-10-30 01:45–01:47 UTC — light checks while timing is queued

Correction to the preceding test-count wording: the Linux main suite ran85
tests total, with84 passing and one Mac-only skip (not85 executed passes).
The subsequent two queue tests increase the lane suite from13 to15; all five
readiness/queue tests passed in the targeted post-change run. Six current
pure CPU checks also passed on the own Mac mirror after an exclusions-only
source sync, `/tmp/agents/irl-shield/gst/mac-queue-pure-tests.log`. No codec,
model inference, install or timed operation ran on Mac in this check.

The observed diagnostic startup first packets were1.221672s GStreamer and
1.208020s FFmpeg; preflight+model warmup6.515297s and9.935976s, respectively.
GStreamer mapped-copy wall p95 was3.089929ms full and1.530329ms reduced; sink
write p95 was6.046594ms (includes mask ZIP). Thread CPU p95 was0.782653ms,
0.225926ms and1.407872ms for those respective operations. Engine poll thread
CPU averaged5.860011ms/output GStreamer vs5.557488ms FFmpeg. Detector actual
fast/accurate rates were7.975/4.000Hz vs7.950/4.000Hz. These numbers retain the
same rejected health/contended scope. Complete startup/stages/raw health/model
metadata and explicit null quality fields are in
`.tmp/gst/diagnostic-score-status.json`. No GPU stretch is justified from
these diagnostics alone.

At the light own-job checkpoint, all five queue submissions were pending with
zero attempts. Root/T3 task status was not polled. No long SH work started.

## 2026-10-30 01:48–01:51 UTC — final lane test receipt and review bundle

All15 current transport tests passed in2.821s under the common SH lease,
inherited T3 slice, nice10 and pools2. This is tiny synthetic CPU/localhost
unit work, not a manual timed benchmark or long quality run. Raw:
`/tmp/agents/irl-shield/gst/lane-final-tests-retry.log`. The first launcher
refused before tests because its fresh systemd-run lacked user-bus environment;
the retry used the already inherited correct T3 slice directly. Both exited.

`git diff HEAD` confirms tracked files unchanged. All14 new paths are inside
packet ownership. A real new-file diff (untracked files are invisible to plain
`git diff`) is retained in `.tmp/gst/review.patch`; direct whitespace/AST/shell
checks passed. No stage or commit was made. `.tmp/gst/HAND_BACK.md` carries
complete source/runtime/model SHA receipts, commands, queue IDs/artifact paths,
health rejection, CPU stages, A/V, unknown quality fields and unfinished work.
`.tmp/gst/grading-commands.md` is the exact deferred Mac grading recipe, not an
executed quality run. Those long SH commands wait until timed queues finish.

01:51UTC hand-back checkpoint: `/proc` inspection found no remaining media
process with this lane's cwd. All own foreground benchmark/control/test/SSH
commands have exited. Five Root-supervised queue submissions remain pending,
zero attempts; `.tmp/gst/queue-own-checkpoint.json` records only these own jobs.
No lane background daemon is retained. Queued source/options and worktree must
remain available for Root's explicitly authorized overnight runner. The source
implementation and producer submission hand-off are ready for Opus review;
acceptance remains open until the missing measurement/quality evidence lands.
