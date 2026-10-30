# Native relay efficiency profiling

This lane supplies an opt-in diagnostic harness. It changes no production
detector, renderer, scheduler, transport or encoder. No bottleneck or speedup
has been measured yet, and no optimization arm has been adopted.

## Execution boundary

Only root submits and runs this job through the canonical EX performance
queue. `python -m bench.efficiency.job` validates the inherited lock descriptor
with `relay.soak.require_queue_lease` and verifies the frozen source manifest
before opening media or creating a CUDA engine. It does not acquire a nested
lock, inspect the owner's relay, read its argv, change system settings, or
connect to Twitch. Stop requests apply to this job's own stop event and child
handles. The full functional gate uses SH separately.

The job requires a nonempty inherited `LD_LIBRARY_PATH` and rejects
`PYTHONPATH`, mixed-site modules, missing runtime dependencies, CPU/GPU ORT
distribution collisions and a missing CUDA provider. It records module hashes
within `sys.prefix` without resolving the interpreter to its base Python.
Root must validate the actual SDK and CUDA libraries before enqueue; a provider
listing alone is not evidence of successful CUDA inference. Preflight probes
all three fixed loopback ports without stopping or inspecting incumbents.

Root must also supply a verified launcher and its hash with evidence of
one physical execution, no retry or automatic fallback, current explicit
queue deadlines and canonical EX-descriptor propagation through py-spy.
The collector binds these receipt hashes and checks its inherited EX lease;
JSON fields alone do not enforce queue policy. Corrected packets remain
blocked until root supplies that launcher. Do not use the expired queue CLI
defaults or schedule the old v2 packets.

The profile uses new loopback MediaMTX ports: RTMP 29351, SRT 28891, RTSP
28555. Binding collisions fail; no incumbent is stopped. The publisher makes
1280×720 H.264 at 30 source slots per second, 3 Mbps, GOP 30, no B frames,
plus silent mono AAC. The image is a moving generated pattern with the
fictional label `CEDAR WAY 417`. It reads no licensed natural or held-out
pixels. Its software x264 encoding load is a separate publisher process,
not a relay cost. This is a phone-like load, not a claim about phone parity.

The real `relay.runtime.make_engine(provider='cuda')` and
`relay.runtime.run(encoder='h264_nvenc')` own the pipeline. Diagnostic archive
is off (`directory=None`). Output goes only to the owned loopback MediaMTX
`shielded` path. A separate observer decodes the output and records scalar
liveness observations without saving video. Observer CPU is also separate.
Neither spatial variance nor successful muxing constitutes a quality score.

Imports/model initialization and MediaMTX startup are recorded separately.
Readiness is the latest first observation of decoded source video, completed
inference in both detector lanes, acknowledged encoded output and independently
decodable output. Only then does 15 seconds of actual warmup begin, followed
by a complete 120-second steady window. The relay's existing `is_set`/`wait`
boundary advances this event controller; no scheduler or pipeline decision
changes. An independent startup fuse bounds absent readiness. Root's hard
deadline remains the bound for a native call that cannot return to that loop.

The receipt records actual elapsed steady time and rejects early termination.
Collection requires positive steady source, successful inference in each lane,
encoded output, LIVE nonslate output and independently decoded nonblack output
populations. It requires valid sender/observer/host/parent/encoder captures,
observed clean process exits, no unfinished spans and no instrumentation errors.
An observer EOF after the completed window is expected writer cleanup; an
earlier EOF fails. The black startup frame cannot satisfy acceptance. This
establishes exercised native-video collection, without assigning privacy,
quality, 30fps or source-to-observer frame matching grades.

Source/output PTS, generation populations and gaps are retained separately;
observer-to-source generation association remains unknown. Crossing spans
remain raw but are excluded from steady totals. Sender scheduling gaps retain
their indices; no catch-up burst conceals a descheduled sender.

## Measurement method and limits

`bench/efficiency/profile.py` installs `sys.setprofile` and
`threading.setprofile` **before** detector and motion thread creation. An
evidence-only hook remains enabled in the control run for readiness and
population observations. A
spawn-safe wrapper shares the observed window with the real encoder worker, without altering its
messages, decisions or encode calls. It records only recognized callable
boundaries and scalar byte counts, never arbitrary locals or credentialed
URLs. Profiling errors are retained and invalidate collection.

The stage table contains decode, color conversion, resize, detector
preprocess/inference/postprocess, tracking, mask rendering, encode, mux and
IPC. Known Python boundaries are selected from the pinned production and
installed dependency source. PyAV/Cython C-call visibility is not yet proven
on the queued SDK: an unobserved boundary remains `unknown`, not zero.

Each span records monotonic wall time and calling-thread CPU. Selected
nested spans are subtracted within that thread. Concurrent threads and
processes overlap, so their wall totals must not be summed into a frame
latency budget. Calling-thread CPU excludes native decoder/ORT worker
threads; it is not full stage CPU. CPU percentages use one CPU core as 100%,
and native process CPU is retained separately. CUDA `InferenceSession.run`
wall time includes transfer and synchronization and is **not** kernel time.

Denominator: successful decoded video `_timestamp` observations inside the
steady window, before the ingress queue drops media. Sent, decoded, offered,
output and observed frames are separate populations. If source frames are
absent, normalized metrics are null. Table counters do not extrapolate from
the engine's bounded historical deques.

IPC spans encompass pickle/socket work and blocking; `serialized_bytes`
counts the observed payload size at send and receive boundaries. Those two
endpoints describe the same transfer and must not be added as distinct
transfers. They are neither RAM copy counts nor PCIe transfer counts.

`telemetry.py` records one-second aggregate CPU counters, PSI for CPU/I/O/
memory, load, swap activity, memory and identity-bound **own** descendant
CPU/RSS/thread counters. It records no external process details or argv.
Departed children can make its live endpoint CPU totals incomplete; root's
canonical queue health and contamination receipt determine quiet/contended
trust. Publisher, observer, MediaMTX, relay and encoder identities remain
distinct. High external CPU alone cannot establish a relay bottleneck.

The optional private py-spy 0.4.1 executable is MIT, downloaded from the
hash-checked PyPI wheel with license and binary hashes in
`out/w11/tools/provenance.json`. Root launches it as the parent of this new
job with `record --subprocesses --threads --native`; it never attaches to an
existing PID. This produces sampled attribution, not exact CPU percentages.
Any ptrace/policy failure is retained; do not change ptrace policy, add sudo,
or retry around a denial. The direct instrumented job is a separate named
packet, not an automatic fallback or hidden retry.

No `nsys` executable was found on PATH in this lane's discovery probe. No
CUDA event or CUPTI capture has run. H→D and D→H transfer counts and bytes
per source frame therefore remain null. ONNX Runtime documents that CUDA
kernel profiling requires a profiling-enabled build and CUPTI; a CPU trace
must not be relabeled as a GPU trace. If root already has supported nsys,
it can supply a separately frozen invocation after checking support and
license. No profiler install, TensorRT adoption or GPU synchronization is
silently added here.

Profiling overhead is uncalibrated. A paired **separate queued** run without
`--instrument` is needed before interpreting instrumented throughput as
performance. The harness permits that control while retaining null stage
metrics; it cannot manufacture missing stage observations.

## Acceptance and follow-up

The initial job packet and source manifest live under `out/w11/`. It is
diagnostic evidence only. A completed command does not pass a performance
gate. After root returns the immutable queue attempt and raw artifacts:

1. Verify source/tool/model hashes and queue contamination/trust. Preserve
   all failed and contended attempts. Report startup and warmup separately.
2. Publish the measured stage table with callable spans, sampled attribution,
   code-inferred bounds and unknown fields explicitly distinguished. Do not
   fabricate an async stage budget or fill GPU fields from host spans.
3. Choose an optimization only if this evidence identifies its cost. Core
   changes remain proposals until root coordinates the released source fences.
4. Require before/after ms/source frame and CPU plus an unchanged independent
   natural/synthetic/area/flicker/real-video/protection scorecard for an arm.
   Missing quality evidence stays null; a quality decrease rejects the arm.
5. Claim 1080 Ti 30fps/NVENC parity only after actual hardware and output
   evidence supports it. Keep generation, hold, deadline and stale-drop
   semantics. Never consume fresh-heldout-v2 before final policy freeze.

Candidate arms remain deferred: GPU residency/resize/color/I/O binding,
bounded batching, motion/ROI scheduling, sharp-frame selection, low-resolution
proposals/high-resolution crops, and shared memory only after a demonstrated
GIL/IPC cost. TensorRT INT8 additionally needs exact installed-version Pascal
support and license/install review; do not assume modern TensorRT supports
Pascal. CUDA EP remains the judges' fallback and no FP16 arm is proposed.

Sources: production `relay/stream.py`, `relay/runtime.py`, `shield/lanes.py`,
`shield/engine.py`, `shield/motion.py`; installed RapidOCR
`ch_ppocr_det/main.py`; [py-spy upstream](https://github.com/benfred/py-spy),
[ONNX Runtime profiling documentation](https://onnxruntime.ai/docs/performance/tune-performance/profiling-tools.html).
