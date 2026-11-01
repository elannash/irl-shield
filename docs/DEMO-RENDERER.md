# W8 prepared source and recording

The W8 fallback has been built and locally rehearsed. Its foundation gate
passed 407 tests, and the conductor cleared its 12-frame three-judge branding
sample. This is neither full-clip clearance nor owner visual acceptance;
the richer W8b source has separate measured results and preview limits below.
The receipts distinguish physical relay observations from incomplete
measurement joins. Detection stays accurate 4 Hz / floor 0.5 / fast 8 Hz;
Patch stays the default, and chat can choose Patch or Bar.

## Prepared clip

`tools/demo_renderer/source.py` builds one 210-second, 1280×720, 30 fps H.264
video without audio. A monotonic pan and approach traverse a single generated
street plate. There is no restart, modulo, concatenation or repeated segment.
This is camera motion over a generated still, not filmed walking footage.
The plate and exact original prompt are in
`fixtures/demo-renderer/ATTRIBUTION.json`; new signs read Cedar Vale / 142 and
Elder Lane / 731. Existing licensed DejaVu Sans Bold supplies the text.

The builder encodes once with NVENC, then decodes the whole result. It requires
6,300 ordered CFR frames and distinct decoded frame hashes, and writes a
`source.json` manifest plus positive, blank and unknown-text controls. Those
checks are structural media checks. Their success would establish neither
brand clearance nor detector effectiveness. The inspected build contains all
6,300 frames at exact 30 fps PTS, with no audio. Any render failure keeps
its receipt; choose a fresh output directory for the next budgeted attempt.

Use the declared Linux Python 3.11 environment and NVIDIA encode support:

```bash
.venv/bin/python -I -B tools/demo_renderer/run.py source --output out/demo/source-01
```

The entry holds the canonical exclusive host lease across imports and the
whole build. It reuses an inherited queue or host-lock lease when present,
and otherwise refuses a busy host. It performs no downloads or queue calls.
Root's test packets additionally pin the SDK, use nice 10 and the agent slice,
and cap native threads at two and OpenCV at one. Builder-specific historical
wrappers and packet seals remain review artifacts; a fresh install does not
need those ignored files.

## Local rehearsal

### W8b opt-in richer source

The explicit W8b route pans over four generated photographic stills in one
static 5760×1024 atlas. Original 1536×1024 PNGs stay in the gitignored cache
`fixtures/cache/demo-w8b/`; source-controlled prompts, hashes, attribution
and the complete motion recipe are in `fixtures/demo-renderer/w8b/`.
No lettering is drawn into this route. The default command above still
builds the original W8 fallback with its original image and motion.

With a provisioned Python 3.11 environment, PyAV/NVENC and the four exact
cached images, the root-owned rebuild command from the repository root is:

```bash
.venv/bin/python -I -B tools/demo_renderer/run.py source \
  --scene-plan fixtures/demo-renderer/w8b/scene-plan.json \
  --asset-base fixtures/cache/demo-w8b \
  --output out/w8b/render-01
```

Use a fresh output directory. Missing assets, incorrect hashes/dimensions,
escaping/symlink asset paths, bad provenance or invalid geometry fail rather
than generate/download anything or silently choose the fallback. Exact image
regeneration from prompts is not guaranteed. Exact video reproducibility
requires the sealed cached plates and a matching encoder environment. A
free checksummed asset payload for judges remains root-owned and pending;
the Git checkout alone does not yet provide those W8b pixels. No paid
generation service is an installation prerequisite or automatic fallback.

The camera uses p=index/6299, left 32→4448, width 1344→1280 and
height=width×9/16. Its top moves from 264 to 50 during an opening eight-second
upward scan, then stays at 50. The shop board enters through the top edge;
later plates enter from the right. The built 210-second source decoded to
6,300 distinct frames with no audio. The shortest continuous interval with
an entire declared label rectangle inside the crop is 130 frames (4.33 s,
the shop board). These approximate annotation rectangles establish framing,
not glyph readability, occlusion or native masking.

Three **static spatial** four-pixel feathers occupy atlas x1518..1522,
2926..2930 and 4334..4338. Native-scale copies of the corner plate's pole
shaft cover these joins using a declared matte. Original asset bytes are
unchanged. The independent assembled review found a depth/viewpoint change
at the first and third joins and recognizable repeated pole texture. This
is a disclosed stitched-still candidate, not a visually cleared filmed walk.
There is no temporal scene switch, crossfade, hard loop, moving foreground
occlusion or physical dolly/parallax. The local rehearsal results below do
not establish complete seam or masking coverage.

`scene-plan.json` preregisters 12 observations for **each** plate, 48 plate/frame
observations. Its raw_samples union states the separate planned count of
unique PNG frame files; actual extraction must report its physical count,
not count a shared frame twice. All three independent judges receive the
raw evidence and the positive/blank/unknown controls. Planned samples cover
entries/exits, full label views and joins. The complete post-warmup window
and long overlap envelopes remain in the native census. Include the small
shop-window glyphs, distant corner fascia and car wheel detail in the raw
inventory whenever visible; the prompt is not evidence of their clearance.

Each decoded frame's source.json row includes `declared_geometry`: exact
crop edges, affine plate/output maps, static feather locations and manual
approximate ROI/reference quads projected into output coordinates. These
are lookup declarations only; they do not attest which frame the native
pipeline selected, what a detector saw or whether a mask covered text.
Actual mask coverage stays null until root joins authentic output pixels
and protection masks to source identities. Every fictional label must be
checked on real non-slate video; all-slate output cannot count as privacy.

The source build and full decode completed, with 6,300 distinct frames over
210 seconds and no audio. Independent PP-OCR, Tesseract 5.5.4 and Apple Vision
processed the 40 unique preregistered raw frames (48 plate observations),
with separate positive, blank and unknown controls. The conductor cleared
that sample. A Tesseract “Hess” token was visually checked and found to be
lichen-speckled stone, not letters. This is a conductor visual ruling for
the sample, not whole-clip certification or owner visual acceptance.

The earlier local rehearsal's metadata recorded 3,600 LIVE frames at 30 fps,
but left 118 source identities unknown. Inspection later found corruption in
that recording and in the fallback recording. Those earlier state/FPS results
never established clean decoded pictures. The intervening framing hypothesis
did not resolve the damaged VCL signatures; its failed receipts are preserved.

After the MediaMTX queue repair described below, a new local-only rehearsal
recorded 3,600 LIVE frames in the full 120-second steady window at 30.0 fps,
with zero PROTECT/HOLD/slates and zero source/output unknowns in that window.
Local publisher mux-start to independent output-decode latency was p50 1.17340 s,
p95 1.18327 s and p99 1.20579 s across those 3,600 identified arrivals. The
original 2.067 ms versus 1.5 ms clock guard remains failed and was not rerun;
these observations are descriptive, not a new W5 qualification or phone latency
claim. Startup and end protection remain in the whole-run census.

The repaired recording supplies all 600 preregistered exact source/archive
preview pairs across four five-second windows, with disclosed sampling cuts.
The earlier playback-aligned preview is historical and is not reused as proof.
The builder inspected four paired source/archive frames, one from each plate,
including their lower image: no periodic corruption band was observed. This
is sampled visual inspection, not a frame-by-frame certificate. The first
long overlap envelope has 44 startup source indices without decoded arrivals;
the other two envelopes have complete identified arrivals. All observed overlap
states are LIVE, but missing arrivals receive no privacy credit.

The sample mask analysis retains verified, uncovered and unknown readings
separately. It uses conservative independent-reading bounding boxes against
archived mask unions; uncovered background pixels are not automatically text
leaks. Whole-interval masking, every label's first/last masked frame, model
projection and physical opacity remain unverified. The source's full-view
rectangle intervals are framing metadata, not substitutes for those proofs.
The four image manifests remain provenance records, not runtime scorecards.

### Existing local sender

`Sender` in `tools/demo_renderer/sender.py` publishes the clip **once** to the
real relay's authenticated RTMP `/camera` path, using the runtime's address and
phone credential objects in RAM. It remuxes the prepared H.264 packets in real
time; it does not run a detector or paint an imitation result. End of source
means end of publication, never a loop. A spawned, owned worker receives a
duplicate of the same EX open description through multiprocessing's FD
transfer. Its private endpoint never enters an executable argument, log,
receipt, fixture or disk config. Native diagnostics are suppressed and core
dumps are disabled. The parent stops and joins that worker, terminating only
its own worker if necessary; a forced stop fails cleanup acceptance.

The fallback's 120-second steady encoder window recorded 3,599 LIVE frames,
zero PROTECT, zero HOLD and zero slates. Independent decoding confirmed
3,592 LIVE frames and left seven unmatched. The stricter source-and-output
content join identified 3,475 of 3,599 arrivals, leaving 124 unknown; latency
p95 1.21525 s and p99 1.22694 s apply only to that matched subset. The original
constant-clock guard failed at 2.067 ms against its unchanged 1.5 ms bound.
Those observations do not constitute a full W5 measurement pass. Reproduce
the build and local run with the commands here and retain a fresh archive;
do not substitute these historical numbers for a new measurement.

The sender's default `local_only=True` requires exact `127.0.0.1` and needs no
Twitch object or LiveApproval. It can be tested against an uncleared candidate
in a local-only rehearsal. This is not permission to publish that candidate.

The real launcher now accepts paired `--demo-source` and `--demo-receipt`
paths with a fresh `--archive` and bounded `--seconds`. Rehearsal requires
explicit `--local-only --host 127.0.0.1` and the frozen detector defaults.
Bandwidth-test mode is rejected for this input. Attended live mode requires
the existing login, fresh broadcaster validation and terminal `LIVE <login>` approval;
the runtime consumes that approval before any sender context starts.
The prepared source omits `--phone-setup`. Local rehearsal keeps the dashboard
active through a subclass that suppresses invitation announcements; its token
stays in RAM. Attended live mode retains the private dashboard announcement so
the owner can pair the phone for the second segment.
No endpoint is parsed from terminal output or supplied in argv/environment.

For a prepared source, the CLI creates the sender context factory for the
runtime. After native encoder startup acknowledgment and construction of the
writer, session and camera reader, the runtime enters the factory with the
same address/phone objects in RAM. Readiness here means initialized transport;
camera data cannot arrive until the publisher starts. Each relay iteration
checks the sender's exit status; terminal completeness is read once. Context
exit joins the sender before source/writer/engine teardown. CLI cancellation
also waits for its initializing model task or running relay before leaving
MediaMTX. Root's packet runs 210 seconds of source within a 230-second runtime
window, including worker startup and a bounded drain. A short or cancelled
publication fails, even if the sender exits normally.

After runtime cleanup, `rehearsal.check_archive` requires nonempty
runtime.json, frames.jsonl, every referenced encoded generation and a complete
sender terminal record. Runtime output counts must match the archive rows and
at least one archived row must claim non-slate LIVE content. Missing, truncated
or all-protective evidence fails. File presence and LIVE metadata do not prove
decoded pixels. A `NOT CLEARED` rehearsal.json states the full row denominator,
startup engine-zero count, explicit ingest-gap count, and count encoded after
the publisher's finished clock. It also counts unarchived engine-index slots
between the first and last observed encoded index, without assigning a source
or cause to those holes. Those counts overlap. Publisher finish does
not identify last decoded input or establish any source-frame join.

After building, run a local rehearsal with fresh output paths:

```bash
scripts/walk-linux --local-only --host 127.0.0.1 --venv .venv --seconds 230 \
  --demo-source out/demo/source-01/source.json \
  --demo-receipt out/demo/sender-01.jsonl --archive out/demo/rehearsal-01
```

Supply verified existing models and MediaMTX using the launcher's named
options when they are outside its default directories. The local-only route
starts no authentication or Twitch forwarder and uses exact loopback input
and output endpoints. This command does not create a network namespace or
claim a native system-call network sandbox. Root's actual rehearsal used a
clean environment without Twitch variables and inherited the canonical EX.
A public unauthenticated `/shielded` reader at loopback is the local viewer;
its recording is a rehearsal receipt, not Twitch player evidence.

The sender JSONL holds source indices/PTS, source-manifest decoded pixel
hash references, publisher packet hashes and mux timing. These are publisher
observations. They establish neither decoder arrival nor model execution.
The complete sender terminal record must say `complete: true`; root checks
its process exit and the real relay's cleanup, output and model receipts.

## Native evidence and P1

`tools/demo_renderer/evidence.py` defines `irl-shield-w8-native-v3` and performs
structural checks only. `validate_structure` always returns
`native_verified: false` and `STRUCTURE ONLY / NOT CLEARED`, including when
an input claims `producer_kind: actual-native-relay`. Test documents are
explicitly `synthetic-test` and cannot be submitted as native evidence.

Every engine selection has `kind: source` with an actually observed source
reference, or `kind: source-less` with `source_id: null` and one of `startup`,
`missing-capture`, `transport-disconnected`. A source-less encoded output
must remain a HOLD/PROTECT slate and has no applied detector IDs. A held frame
with a genuine selected input can keep that input reference. A missing output
is an explicit half-open `gaps` range with `source_id: null`, never a made-up
capture. `window` states the entire engine-index interval; emitted indices
and gap ranges must account for it. Preserve startup, protection, reconnects,
archive loss and gaps in the receipt even if a presentation crop starts later.

Sources record observed source index, ingest generation/PTS and input VCL
hash; detector rows bind model hash, lane, engine selection and source ID;
output rows bind egress identity, session PTS, actual final pixels/mask and
encoded VCL hashes. Root's collector must extend this structural minimum with
actual detection-completion/deadline records, projection-to-mask associations,
post-presentation/late-HOLD output observations and content/clock joins. A
self-authored hash or matching JSON field cannot establish those facts.
Reproduce the local transport and archive evidence with the build and
`scripts/walk-linux --local-only` commands above. They do not produce the
remaining detector-completion, projection-to-mask or native content joins;
those require a reviewed observer and its raw receipts. Missing joins remain
unverified, never inferred from source timing or renamed offline records.

## Branding evidence

The independent judges are Tesseract 5.5.4 PSM11, Apple Vision accurate and
independent PP-OCR. For the fallback, all three completed 12 raw sampled frames
and positive, blank and unknown-text controls. PP-OCR and Vision read only
the intended fictional names and numbers. Tesseract's additional readings
were retained and reviewed by the conductor as texture noise; the conductor's
logo eye agreed. This clears the sampled fallback frames, not the whole clip,
and does not transfer to W8b. The richer clip needs 12 observations per plate
and a separate human semantic/logo verdict.

`branding.retain_raw` copies each supplied judge JSON **byte for byte** and
hashes it. Retain every confidence, unknown, empty result, error and original
observation from every independent judge before any threshold, allowlist,
deduplication or canonical filtering. The envelope names `judge`,
`source_manifest_sha256`, `collection_stage: raw-before-filters` and the full
`observations`. Include every sampled frame and all three controls, exact
engine/model/code identities and sampling coverage in those raw envelopes.
A successful retention call does not attest those collector claims or confer
clearance. Keep unknown text available for human inspection. Archive a
separate human logo-eye artifact with reviewer, exact source hash, viewing
coverage, findings and verdict. A missing judge, error, unresolved unknown or
missing human review remains visible. Root owns the canonical clearance
verdict and bindings after inspecting the raw evidence. No old review or
historical Mac result clears this output.

## Attended recording

An attended recording can use the prepared clip followed by a short live
phone segment. First obtain source, brand, native and visual acceptance,
then follow the authenticated broadcaster's live-approval flow.
The prepared clip's first 180 seconds are the uninterrupted recording window;
its extra 30 seconds cover player startup. If player startup consumes that
margin, stop and prepare a fresh take. Never loop or splice a take to make
it appear continuous. Preserve the entire raw recording and failed takes.

1. On an owner-present, explicitly authorized live session, root uses the real
   Twitch flow and the fresh `LIVE <login>` confirmation. Bandwidth-test mode is
   not a public Twitch player demonstration. Keep the setup terminal,
   credentials, QR/pairing and private dashboard out of all capture sources.
   Only after the clip's branding and visual review, use the same launcher
   with `--twitch-live`, the prepared source/receipt/archive options, a fresh
   receipt/archive destination, and `--seconds 600` through `infisical run --`.
   Its normal broadcaster login and fresh `LIVE <login>` prompt still apply. The source
   publishes once for 210 seconds; the relay stays available for the phone's
   following five minutes. No owner-attended live run has been validated here.
2. Record a clean video canvas from the genuine Twitch player alongside its
   genuine chat. Use only the minimum approved player/chat area: browser,
   Twitch and third-party chrome/emotes can introduce logos. Keep notifications
   and music off. Preserve an untouched private raw take; produce a separately
   reviewed crop for submission. The final crop needs its own brand/logo eye.
3. Capture the source preview separately from the exact same prepared file.
   Show Before / Shielded with source index/PTS only after root's native
   input/output join identifies the pair. Player wall-clock timestamps alone
   cannot align frames across Twitch latency. Leave unbound regions or gaps
   labeled unavailable. Never construct an After image by painting test boxes.
4. After stable protected LIVE video is visible, an authenticated moderator
   sends `!shield hold`. Record the chat event and the resulting real HOLD
   slate. An ordinary viewer cannot perform this action. The broadcaster
   sends `!shield resume`; moderator resume is not authorized by current code.
5. Record `!skin bar` and `!skin patch` from real viewers and the resulting
   output. Voting uses one current vote per user in a 60-second window and
   retains the incumbent on ties. For a deterministic demonstration, the
   moderator may additionally send `!skin lock bar`, then `!skin lock patch`,
   then `!skin unlock`; keep those commands visible so a lock is not presented
   as a vote result. Only Patch and Bar are in `CHAT_SKINS`.
6. End prepared publication once. Keep the transition to transport protection
   visible, then switch to an approved phone source. Keep private content out
   of the published take and obtain the participant's review before sharing.
   No hard loop, simulated chat,
   fake Twitch UI or substitution of a local reader for Twitch evidence.
7. Root seals the raw player/chat take, native capture/selection/detection/
   projection/paint/encoded-output records, sender receipt and exact source,
   model and code hashes. Verify native content joins, real LIVE content,
   before/after legibility, HOLD/resume authority and displayed skin behavior.
   Inspect coverage and gaps; all-slate output supplies no LIVE success.
   Independent Emil review and the owner's eye decide presentation acceptance.

No recording, live approval, external write, W1 tuning or new visual direction
is authorized by running a local preparation command.


### MediaMTX keyframe bursts

The outgoing MediaMTX packet queue is 1,024 entries, a power of two. The earlier
128-entry override could truncate large keyframe bursts even with RTSP over TCP.
The initial source and local remux decoded cleanly, while an independent camera
RTSP reader already showed lower-image corruption and slow-reader warnings.
The original configuration did not record a latency or memory rationale for 128.
The larger capacity absorbs bursts; it does not insert a fixed playout delay.
MediaMTX 1.21.3's [upstream configuration](https://github.com/bluenviron/mediamtx/blob/v1.21.3/mediamtx.yml)
uses 512 entries by default. The conductor selected 1,024 to allow larger phone
keyframes as well as the demo source.

With `--archive`, the native CLI writes `mediamtx.json` after stopping the server.
It contains fixed warning counts, the latest 64 warning events, close codes,
diagnostic drop counts and the configured queue size. It retains no raw server
lines, connection identifiers or credentialed URLs. A warning count is an
observation, not a clean-video certificate.

The controlled 128/1,024 comparison used the unchanged W8b source, a seeded
approximately 610 KB two-slice keyframe stream, and a 720p phone-shaped stream
at measured 5.35 Mbps with a two-second GOP. At 128, both large-keyframe cases
showed byte/pixel damage and nine slow-reader warnings each. The phone-shaped
case was a healthy control at both sizes. At 1,024, all observed VCL payloads
and all compared whole/lower decoded pixels matched the independently decoded
sources, with zero warnings. The decoded comparison tails contained 300,
270 and 240 frames respectively after their first joined IDRs; pre-join frames
are not claimed clean. The builder's eye confirmed clean lower images at the
fixed comparison frame. Actual Moblin hardware remains unqualified here.

The helper retains untimed startup packets and uses unique complete content
for identity; unresolved observations fail. It keeps the publisher alive until
the fixed receive window completes, then closes that publisher before stopping
MediaMTX. An earlier immediate-EOF experiment truncated the phone-shaped
stream's final slice without a slow-reader warning; that separate teardown
finding is retained and is not credited as a queue-overflow red.

The new native archive's warning counters were empty. Its legacy aggregate
`diagnostic_drops` was 71; that counter mixes bounded-history evictions with
oversized input chunks and does not identify their individual causes. The
value is preserved, not relabeled as zero loss. The earlier recordings remain
historical evidence and must not be presented as clean video.

`bench/keyframe_probe.py` reproduces the transport check with CPU/libx264
fixtures and the actual MediaMTX path. These are literal job arguments for an
existing canonical EX runner, not standalone shell commands. The runner must
supply its inherited `IRL_SHIELD_PERF_QUEUE_LEASE_FD`, nice 10, native thread
limits of two, and `OPENCV_FOR_THREADS_NUM=1`. Use a provisioned Python 3.11
environment and fresh output directories, preserve failures, and cap each job
at one execution. The W8b source must already be built at the specified path.

```bash
.venv/bin/python -I -B bench/keyframe_probe.py prepare --root "$PWD" \
  --fixtures /tmp/agents/irl-shield/keyframe-proof/fixtures
.venv/bin/python -I -B bench/keyframe_probe.py run --root "$PWD" \
  --fixtures /tmp/agents/irl-shield/keyframe-proof/fixtures \
  --results /tmp/agents/irl-shield/keyframe-proof/current-queue
```

The controlled old-queue proof changes only the product queue setting to 128,
then restores 1,024 byte for byte and reuses the exact fixture files. The helper
has no queue override or automatic retry. A fixture/connection/cleanup failure
never counts as the expected corruption red; that requires actual byte or pixel
damage together with a slow-reader warning. Inspect the saved source and RTSP
keyframe PNGs, including their lower image, before accepting a green result.
