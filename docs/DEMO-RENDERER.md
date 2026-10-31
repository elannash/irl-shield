# W8 prepared source and recording

This source is **NOT CLEARED**. Preparation is based on main
`92652e8aaf3346e17bca4f7fe271df45fef81952`. The source build and local relay
rehearsal have run; branding review and the integrated gate remain pending.
Root's receipts distinguish physical relay observations from incomplete
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

The sender's default `local_only=True` requires exact `127.0.0.1` and needs no
Twitch object or LiveApproval. It can be tested against an uncleared candidate
in a local-only rehearsal. This is not permission to publish that candidate.

The real launcher now accepts paired `--demo-source` and `--demo-receipt`
paths with a fresh `--archive` and bounded `--seconds`. Rehearsal requires
explicit `--local-only --host 127.0.0.1` and the frozen detector defaults.
Bandwidth-test mode is rejected for this input. Attended live mode requires
the existing login, fresh naie validation and terminal `LIVE naie` approval;
the runtime consumes that approval before any sender context starts.
The prepared source omits `--phone-setup`. Local rehearsal keeps the dashboard
active through a subclass that suppresses invitation announcements; its token
stays in RAM. Attended live mode retains the private dashboard announcement so
the owner can pair the phone for the second segment.
No endpoint is parsed from terminal output or supplied in argv/environment.

The CLI supplies an optional `phone_input` context factory to the actual
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
The remaining observation seams are listed in the historical
`out/w8/current-main/ROOT-HOOK.md`; local hook implementation and the remaining
collector gap are recorded in `out/w8/local-hook-main92652/ROOT-INTEGRATION.md`.
Missing native joins remain blocked, never inferred from
source timing or renamed offline detector records.

## Branding evidence

The canonical three independent judges remain Tesseract 5 PSM11, Vision
accurate and independent PPOCR. Root reports the Mac online and r2 grader
installed (`7d6d4c8e`); current collector bindings and this clip's evidence
remain pending. The child's work makes no Mac/SSH calls. The root's one Mac
preflight is a fresh-v2 prerequisite, not W8 clearance or W1 adoption.

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

## Owner-started Sunday recording

The owner chose prepared clip followed by about five minutes of phone at
home on **Sunday November 1, approximately 15:00 America/Los_Angeles**, on
`naie`. Root first obtains current source/brand/native/visual acceptance.
The prepared clip's first 180 seconds are the uninterrupted recording window;
its extra 30 seconds cover player startup. If player startup consumes that
margin, stop and prepare a fresh take. Never loop or splice a take to make
it appear continuous. Preserve the entire raw recording and failed takes.

1. On an owner-present, explicitly authorized live session, root uses the real
   Twitch flow and the fresh `LIVE naie` confirmation. Bandwidth-test mode is
   not a public Twitch player demonstration. Keep the setup terminal,
   credentials, QR/pairing and private dashboard out of all capture sources.
   Only after the clip's branding and visual review, use the same launcher
   with `--twitch-live`, the prepared source/receipt/archive options, a fresh
   receipt/archive destination, and `--seconds 600` through `infisical run --`.
   Its normal naie login and fresh `LIVE naie` prompt still apply. The source
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
   visible; then root switches the real phone input to the owner's home for
   approximately five minutes. Do not record home identifiers/private content
   for publication until the owner reviews it. No hard loop, simulated chat,
   fake Twitch UI or substitution of a local reader for Twitch evidence.
7. Root seals the raw player/chat take, native capture/selection/detection/
   projection/paint/encoded-output records, sender receipt and exact source,
   model and code hashes. Verify native content joins, real LIVE content,
   before/after legibility, HOLD/resume authority and displayed skin behavior.
   Inspect coverage and gaps; all-slate output supplies no LIVE success.
   Independent Emil review and the owner's eye decide presentation acceptance.

No recording, live approval, external write, W1 tuning or new visual direction
is authorized by running a local preparation command.
