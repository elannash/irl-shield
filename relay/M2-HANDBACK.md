# M2 relay hand-back

**Interim verdict: the new RTMP soak is red after 1,007.492 seconds and
30,001 encoded frames. Reconnect happened about 339 seconds earlier; generation 2
continued cleanly, so an immediate fatal reconnect regression is not established.
The long-origin and high-output-PTS local probes pass. The current patch improves
blocked-worker/input diagnostics only; it is not a claimed runtime fix. Full
Linux functional gate 67 passes. Gate2, SRT, independent privacy and Q remain
unqualified.**

## Checkout, ownership and deadline

Requested and actual branch: `elannash/m2-relay`. HEAD is unchanged from the
requested base, `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`. Dedicated worktree:
`WORKTREE_t3-ae860af9`. The first operation verified
pwd, branch, exact HEAD and clean status; the prepared branch was renamed in
place. Continuation checks preserve all uncommitted work. No staging, commit,
push, PR, merge or shell worktree creation/removal occurred.

All edits are in `relay/`, `scripts/m2-*`, `tests/m2/` and owned ignored scratch.
Engine, scorer, judges, caches, root requirements and root README are unchanged.
The original Mac transport remains unchanged. This new launcher targets Linux;
no Mac Swift/VideoToolbox gate ran. The original start was approximately
2026-10-30 03:55 UTC; the original eight-hour cutoff is approximately 11:55 UTC,
earlier than Friday 07:00 PT. Neither model changes nor budget increases reset it.

All newly authored paths remain untracked for Opus to review and commit. Source
identity is the working-file hashes, not HEAD alone. The frozen implementation
snapshot is `.tmp/m2/source-at-requalification.json`; each native provenance
records its own source, model, dependency and argv hashes/versions.

## Implementation and integration

MediaMTX v1.21.3 is downloaded and hash-verified in `.tmp/tools/`. RTMP/SRT bind
only the assigned Tailscale address or IPv4 loopback. The sole internal reader
uses authenticated TCP RTSP on `127.0.0.1:18554`; UDP/multicast and extra services
are disabled. Startup proves the new process owns the exact listener inodes and
rejects occupied ports. No incumbent is stopped.

Generated phone credentials publish only `camera`; internal credentials read
`camera` and publish `shielded`; viewers can read `shielded`. Both paths disable
publisher replacement. Credentialed configuration travels through stdin, never
files or argv. Interactive `--phone-setup` requires a TTY and displays phone
credentials once. Automated tests suppress it. Core dumps are disabled before
credentials are generated.

MediaMTX stdout/stderr is consumed in memory and reduced to a bounded ring of
64 fixed-code close events. Lines are bounded at 8192 bytes, connection mapping
at 128. Only protocol, known path, fixed code and monotonic time survive; raw
lines are discarded. Authentication, timeout, collision and slow-reader reasons
have fixed classifications; unknown messages become a fixed generic code.
Startup retry noise can evict initiating events, a known diagnostic limit.
Libav logging callbacks are disabled; native exceptions cross as fixed codes,
class names, numeric errno and controlled operation names, never raw text.

One shared `MaskingEngine` owns the pixels. Cold startup submits a black frame
at the configured shape/PTS under transport HOLD. The sole sink consumes only
`engine.poll` results. A deliberate decoded-frame bypass fails the structural
single-writer check; source was restored byte-for-byte and rerun green. Input
is bounded at eight events; overflow invalidates a generation. The PCM ring is
192,000 samples; disconnect/reconnect clears old-generation audio. Each output
carries 1,600 mono 48kHz samples at its video PTS, with silence for missing audio.

Egress owns one hardware encoder in a killable process, one frame in flight,
and bounded reply/cleanup timeouts. Archive and network remux use the same
encoded packets, headers and keyframe flags. Native Linux jobs use NVENC and
Tiny8Hz640/Small4Hz960, D1, phase320/floor.05/pad.3/B6/A30. This policy is
**unqualified**; CPU provider fallback remains allowed and root Q can replace it.
No all-slate result qualifies as a privacy pass.

The one-command setup/run recipe is [README.md](README.md). M3 integrates
through `relay.runtime.run(..., control_ready=register_callbacks)` in the same
process. The callback receives `RelayControl.hold(active, source, reason)` and
`set_stream_key(key_or_none)`. Holds remain separate by local/chat/EventSub
source; reconnect clears only transport HOLD. The Twitch destination is an
in-memory stub enforcing `?bandwidthtest=true`, with no network implementation,
login, key acquisition or Twitch contact. Infisical integration remains M3/root
owned; no secrets were accessed here.

## Verification and test accounting

Conductor increased the ceiling from 40 to 52, then 58, then **62**. The count is
**59 executed before the final soak/ACL submissions**. Pre-exec readiness
rejections spend zero; every executed retry spends one. At most one physical
contended-soak retry is authorized, never a third physical soak.

| Accounting positions | Work and result |
| --- | --- |
| 1–38 | Parent probes 01–20 plus 18 implementation-child invocations; all red receipts retained |
| 39–42 | Encoder repro/fix and affected suite; 42 passes all 16 M2 tests |
| 43 | Full Linux functional: 96 default tests, one Mac skip; 16 M2 tests and compileall pass |
| 44–47 | Four original queued native executions, all red; two readiness rejections excluded |
| 48–50 | Local capture diagnoses whose filenames are 44–46: empty-file failure, real SRT remux failure, raw MPEG-TS fix/real decode |
| 51–52 | All 16 affected M2 tests pass after capture and safe-diagnostic changes |
| 53 | Diagnostic pilot: 38.0375s/955 frames, contended, network-mux broken pipes |
| 54–55 | Four-second publisher gap: red with 3s timeout, green with 10s timeout |
| 56 | Full Linux functional passes again: 96 default tests, one Mac skip; 16 M2 tests; compileall |
| 57–58 | First 60s RTMP/SRT A/V executions; both contended; RTMP exit0, SRT exit2 |
| 59 | Exact captured backward-DTS replay into real local Matroska mux reproduces ValueError(errno22) |
| Reserved | Soak and ACL first executions, plus one executed retry; finalized count awaits their receipts |

Raw parent logs are under `/tmp/agents/irl-shield/m2-relay/`. `LOG.md` is the
chronological ledger; the implementation-child hand-backs retain their exact
commands and limits. Parent full-gate argv/exit codes are in `43-full-gate.json`
and `56-full-gate.json`, with complete `.log` files. The subsequent native-auth
diagnostic-contract update is covered by the pending real ACL matrix rather
than a claim about the earlier unit run.

Recent exact commands:

```sh
env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 10 .tmp/m2/py311/bin/python .tmp/m2/full-gate-56.py
REPO_ROOT/scripts/host-lock exclusive env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 10 .tmp/m2/py311/bin/python .tmp/m2/repro-publisher-gap.py /tmp/agents/irl-shield/m2-relay/54-publisher-gap-red.json
REPO_ROOT/scripts/host-lock exclusive env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 10 .tmp/m2/py311/bin/python .tmp/m2/repro-publisher-gap.py /tmp/agents/irl-shield/m2-relay/55-publisher-gap-green.json
env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 10 .tmp/m2/py311/bin/python .tmp/m2/repro-capture-dts.py /tmp/agents/irl-shield/m2-relay/59-capture-dts-repro.json
```

Exact literal queue argv is retained in `.tmp/m2/queue-producers.json`,
`session2-diagnostic-command.json`, `session2-av-commands.json` and
`session2-final-commands.json`. No queue-owned command reacquires the lease.
The harness validates the inherited canonical EX descriptor and preserves forced
semantics. Native jobs run nice10 in `app-t3code-agents.slice`, with native
worker settings capped at two. Recorded total process thread counts include
other runtime/helper threads and can exceed two.

## Diagnoses and known failures

The native direct-RTMP PyAV reader crashed in `av_dict_free` inside
`InputContainer.__cinit__`. GDB receipt 19 and installed PyAV source support an
inferred dynamic stream-option allocation/free mismatch; no library was patched.
Conductor's protocol-conversion prediction was tested and the live reader uses
RTSP/TCP only. Exact Python/PyAV/FFmpeg library versions are in
`.tmp/m2/native-version-receipt.json`. Native crash receipts are retained.

Original SRT side captures wrote empty Matroska files: startup decoder templates
had 0×0 video dimensions/no extradata, and the first AAC remux raised errno22.
Local real-socket reproduction confirms it. Recording native MPEG-TS payload
bytes directly to `.ts` removes the premature-container-header dependency;
local socket capture and closed-file video/audio decode pass. This capture fix
is separate from the later RTSP timestamp defect below.

Pilot 53 surfaced sender and encoder `network-mux` BrokenPipeError(errno32).
Phone `camera` and egress `shielded` paths are distinct, override is false, and
failure preceded every planned fault. Its server logs were discarded, so the
pilot's initiating server close cannot be recovered. Local 54 reproduces a
four-second publisher pause causing fixed `io-timeout` then BrokenPipe under
3s readTimeout. Identical driver/source 55 resumes 150 packets under 10s.
Read/write bounds now match the pinned [MediaMTX 10s defaults](https://github.com/bluenviron/mediamtx/blob/v1.21.3/mediamtx.yml#L20-L23).
Privacy still belongs to engine deadlines, independent of connection timeout.
This proves that disconnect trigger, not that every earlier failure shared it.

**SRT A/V remains red and is not qualified for a walk.** Its independent RTSP
capture records video DTS 83,970 then 83,229 at timebase1/90000 immediately
before remux failure. Local59 replays that exact DTS sequence with actual
archive video packets and reproduces ValueError(errno22) at the same step.
Its payload is the archive's packets, not a reconstructed raw RTP payload.
No timestamp clamp or misleading continuity fix was applied. The replacement
SRT sender later fails in network-mux after eight frames; its originating cause
remains unverified.

The **main** reader decodes camera RTSP directly and does not perform the side
capture's Matroska remux. It processed SRT generation1 (970 offered frames,
701 LIVE outputs, last LIVE PTS36.0). Its transport drops 17 decoded frames
whose mapped index does not advance; the RTMP run drops175, so this counter
cannot identify the exact raw DTS defect. No main-input raw packet/PTS manifest
exists; whether it encounters that same raw regression cannot be proved from
these receipts. After HOLD release at44s all remaining684 SRT outputs are HOLD,
so SRT reconnect usability is not established. RTMP is the only current walk
candidate, still subject to endurance, cadence and independent privacy gates.

## Native results and per-criterion Gate 2 status

Detailed receipt audits: [QUEUE-HANDBACK.md](QUEUE-HANDBACK.md),
[RUNTIME-DIAGNOSTIC-HANDBACK.md](RUNTIME-DIAGNOSTIC-HANDBACK.md), and
[AV-REQUALIFICATION-HANDBACK.md](AV-REQUALIFICATION-HANDBACK.md).
All four original seals (82 files), pilot seal (19 files), and both first A/V
seals (50 files) were independently verified by parent against original stdout
anchors. Integrity proves frozen bytes, not transport or privacy success.

The original soak executions stopped at30.228s/715 output frames and435.290s/
12,909 frames under contention; neither reached20min or completed the fault
schedule. Their originating generic runtime errors remain unverified.

The new RTMP 60s job completes functionally under contention: 2,005 encoded
frames; decoded RTSP/SRT captures contain1,915/1,910 video frames over63.816/
63.633s. Flash/beep median offsets4.479/1.479ms, absolute p95 6.012/9.013ms,
19 pairs per capture. PTS increases; maximum gaps50/34ms. Both deliberate kill
and reconnect occur, with203 manual-HOLD frames and zero metadata violations.
This is useful partial evidence, not uncontended Gate2 qualification.

| RTMP Gate2 criterion | Current verdict before final queue results |
| --- | --- |
| Native20min, uncontended | PENDING; submitted, not claimed |
| Bounded memory and queues | PARTIAL: input high-water8/8, audio capacity192000, declared engine cap68; sampled main RSS922588KiB (~901MiB). Encoder-worker/spawn-helper RSS and GPU/VRAM are not sampled, no20min stability proof |
| Sender kill, lane stall, reconnect survive | PARTIAL:60s RTMP faults complete,120/120 checked stall-window rows protected, HOLD metadata violations0;20min result and independent pixel verification pending |
| A/V offset | MEASURED on the60s subset: RTSP median4.479ms/abs p95 6.012ms; SRT median1.479ms/abs p95 9.013ms;19 pairs each. Endurance offset pending |
| Zero egress gaps above10s timeout | OBSERVED on populated60s captures; no endurance claim |
| Fail-closed frames at cadence | NOT QUALIFIED: protected encoded-wall gaps reach572.7ms;19 gaps exceed2/30s. Protection metadata is not independent pixel/OCR proof |
| Zero readable synthetic labels / real video | PRIVACY PENDING root corrected independent/all-leak scorer afterPR4 merge; Q unqualified. LIVE/spatial guards reject all-slate output but cannot establish privacy |

Encoded monotonic timestamps are measured after encode+mux; frame PTS is a
separate clock. RTMP maximum egress write/ACK wall time is580.2ms and maximum
encoded gap572.7ms; presentation batches also lag. These measurements do not
isolate CPU starvation, GPU, IPC or network blocking. No pure-starvation claim
or verified process-priority requirement is made. Walk qualification requires
an uncontended host meeting the queue's >=80% idle and>=4GiB readiness conditions
and native cadence evidence; raising priority was not tested or performed.

## Final queued producers and live state

Session2: `REPO_ROOT/.tmp/irl-shield-builder-m2-queue-2`, now
**SEALED** after the complete M2 producer set. Root owns runner3442769 and is
watching the retry limit. New explicitly authorized foreground jobs:

- RTMP20min `5457243dcb624b4fbffa927fad880bc2`; output
  `.tmp/m2/gate2-v2/m2-v2-soak/attempt-N/`.
- Real RTMP/SRT publish/read-ACL matrix on loopback and `<tailnet-ip>`
  `046a95aa58364472a2318e26947c457c`; output
  `.tmp/m2/gate2-v2/m2-v2-read-acl/attempt-N/`.

No parent observer or local diagnostic process is retained. The receipt-only
children's observers exited; neither controls the runner. Queued child PIDs are
assigned at execution and will be audited from receipts. No stored PID is killed
without matching identity. Root-only safe stop, **not executed by this lane**:

```sh
REPO_ROOT/scripts/perf-queue --queue-dir REPO_ROOT/.tmp/irl-shield-builder-m2-queue-2 stop linux
```

Root will close the soak after its second contended physical result before a
third. Old diagnostic and A/V producers are closed-one-shot; no repeated native
execution is hidden as readiness rejection. Final totals, resource/PTS/A/V
criteria, cleanup and retained PID details await these final receipts. The
runner's09AM cutoff does not extend the M2 timebox.

## Dependencies, licenses and artifact scope

No new detector or model was introduced. Root pinned CUDA12.4/ORTGPU1.20.2 and
model cache are reused read-only; no global package, driver, system CUDA, sudo,
paid service, account or external secret access occurred. PyAV16.0.1 is installed
in owned `.tmp/m2/py311`; the initial unsuitable Python3.14 environment is unused.
The actual install URL/wheel SHA is retained in `av311-install.json` and
`.tmp/m2/installed-tool-receipt.json`. PyAV is BSD-3-Clause; its Linux FFmpeg
wheel includes GPL components/libx264, so LGPL-only labeling is insufficient.
No binary is committed or redistributed by this lane.

MediaMTX v1.21.3 is MIT. Archive SHA256
`0a2ea7eba96023631efa1bea7804823a9145b043b6646a8a05798d4ac24ed635`;
binary SHA256
`bfa372a169751bbf6da2ebddcbcd2f7d3ab3dca3cc553022162eda36fe03e73d`.
System libsrt1.5.4 is MPL-2.0 with BSD portions, no install/redistribution;
library SHA256
`30af7a9de19c8644f76fcb3f8c0b269bc48b98271deaca497cfdc6ff4ed099b6`.

Existing PP-OCRv6 Tiny/Small artifacts are Apache-2.0. Tiny SHA256
`193bab7a04fca699a6c82e6abb5b81bdb28177f0abd4062552b04908dafb19f8`;
Small SHA256
`d73e0058b7a8086bbd57f3d10b8bcd4ff95363f67e06e2762b5e814fe9c9410e`.
Pinned model revisions, URLs, parameters, providers and license links are in each
native provenance and `models/manifest.json`; existing dependency license
records remain in `models/licenses/dependencies.json` and `bench/PORTABILITY.md`.

The tune fixture sf-market is CC BY3.0, SHA256
`bed20032b30bcdfebb32f137809b71cedf8486c7881020e5e955a91aa28aca7c`.
Synthetic labels/stamps/flashes/timing tones are original CC0 generator output;
source audio is discarded and no music is used. Every fixture and derivative
remains **BENCHMARK-ONLY, not demo-ready**. No demo-footage or public-video claim
is made. Code/docs remain English and the repo stays private.

Outstanding: audit final queued receipts and processes; corrected independent
privacy grading/Q; RTMP cadence qualification and complete resource coverage;
SRT timestamp/reconnect limitations; Mac gate; live phone and Twitch integration
outside tonight's authorized scope. No final Gate2 pass is claimed.


## Continuation after the first new soak (current)

Opus committed and pushed the frozen source checkpoint as
`d4a28a99bdda0bc44a685f31cd971babf1263781` on this branch. This was the
conductor's action, not a commit/stage/push by this implementation lane. Further
source changes are uncommitted diffs against that checkpoint; the original
project base remains ec1d1f96a1c29ab82109c66f27064f3fd6cb326d.

Conductor raised the test ceiling to72, unchanged original timebox. Current
executed count is66 before the still-pending ACL job: prior59 + first soak1 +
six local invocations whose receipt numbers are62–67. Number61 is reserved for
the asynchronous ACL invocation and was not charged before execution. The new
soak producer is closed-one-shot; no blind native retry was submitted.

The soak ran1,007.492s, not20min, and produced30,001 manifest frames before
`egress-write-timeout`. Maximum write/ACK time6.217s includes worker cleanup;
old timeout receipts do not identify the active native operation. `input-timestamp`
is a last input code with no error timestamp in that source version. Hold/kill/
reconnect/release occurred664.167/665.060/668.019/671.015s. Failure followed
reconnect by~339.2s; final frame index30000/PTS1000 was LIVE, and generation2
sender stopped cleanly after10,033 frames. A direct causal link to reconnect is
not proved. Main106sessions/242disconnects/13video drops show input instability;
the originating encoder stall remains unidentified. Root closed the retry.

62: short real MediaMTX RTMP→RTSP→sharedengine→CPUegress test with generation1
originPTS600s, kill, and generation2origin0. Runtime12s completed,347frames,
2sessions, but the helper's cleanup attempted Event.set on the already-SIGKILLed
sender and blocked. All four owned process identities were matched and stopped;
no survivor remained. This is a failed helper invocation, not reproduction of
the original encoder timeout. 63 fixes only helper cleanup and passes350
contiguous output frames/2sessions/0video drops, max encoded gap164ms, all
processes/threads stopped. It tests high source timestamp origin, not600s wall
endurance. 64 tests actual engine-produced HOLD frames across outputPTS999.867
through1002.033: libx264 and NVENC each encode and decode66frames successfully.
Both simple timestamp hypotheses are therefore insufficient to reproduce the
native stall. Neither synthetic test qualifies privacy or source-rate cadence.

Current source patch (`relay/stream.py`, `relay/runtime.py`, existing
`tests/m2/test_stream.py`) retains only numeric worker progress in shared memory:
active encode/mux operation, operation start time, active/completed frame index.
A timeout now reports that operation even when the worker cannot reply. Input
failures include generation and monotonic time; missing/nonincreasing input PTS
are counted with their exact numeric values and generation, without clamping or
changing timestamp mapping. The public Egress/RelaySession/callback interfaces
remain compatible. No engine/scorer/cache change or underlying cause fix occurs.

65 extends the real stalled-RTMP handshake regression: red because timeout lacks
`operation`. 66 passes all4stream tests, with operation `network-startup` surfaced
safely. 67 fullLinuxfunctional passes96defaulttests(oneMacskip),16M2tests and
compileall. Receipts62–67 and commands are in the parent receipt directory;
helpers are `.tmp/m2/repro-long-reconnect.py`, `repro-high-egress-pts.py`, and
`full-gate-67.py`. Source hashes are recorded in each local reproduction. Mac
Swift/VideoToolbox remain unrun; no cadence or native Gate2 pass is asserted.

A zero-test-budget read-only Ultra child is inspecting the sealed native timeout
and checkpoint source for a falsifiable next probe. No new20min producer will
be called a fix until the actual failure is reproduced or otherwise identified.
The existing read-ACL matrix remains root-owned queued work. Original deadline
~11:55UTC remains unchanged, earlier than07AMPT.


## Current recovery order and ACL audit

Conductor extended this fix to Friday08:00PT (2026-10-30T15:00Z) and raised the ceiling to76. Current actual count is69, with one red test invocation70 reserved for the test child.

Parent verified the ACL job against original stdout seal a5fe28931a2f0abecbfaa65eb64a32adaa9db514690cf944b501f9b6a425af8b and its exact one-file inventory/hash/size. Both allowed hosts pass real RTMP/SRT publication and authenticated RTSP three-packet reads, denied anonymous/bad/phone camera reads, denied wrong-role/path publishers, exact bindings, credential-absence checks, and server exit0. Accounting is valid, uncontended, forced=false; other-busy mean15.851132%/max18.974756%. This is a socket ACL/binding pass, not privacy or endurance. Audit: .tmp/m2/acl-parent-audit.json. Root runner3442769 exited empty/sealed.

Probe68 reproduced steady-state network-mux blocking after a fragmented valid RTMP control message (90 warm-up ACKs, then93 versus300 for the full-control condition). Historical attribution remains unproved. A bridge experiment69 was already running when conductor directed otherwise; it failed startup and its red receipts remain. The production bridge and import have been REMOVED. Candidate parser code is retained only as a test fault fixture in ignored scratch; no production RTMP parser is proposed.

Bounded recovery is staged ONLY in .tmp/m2/recovery/{stream,live,runtime}.py, not active. Only the writer restarts after its old process is reaped. Failed/precomputed frames are discarded; the next fresh engine result follows current control/HOLD state. Five reconnects per60s,250ms backoff, separate archive generations, appended mask/PTS rows, fixed-code operation-aware recovery events. No timestamp clamp or engine/ingest restart. Public entry points remain; write returns False to signal batch discard.

The Ultra test child owns tests/m2/test_recovery.py/helper and RECOVERY-TESTS-HANDBACK.md. It has ONE red invocation70 against current pre-recovery parent source. Same68 fault bytes/six-second delay; a six-second backpressure fault after actual buffer saturation; HOLD applied while blocked; real recovery limit if feasible. The fixture must accept reconnections, while injecting each fault only once. Parent audits/copies, applies staged recovery, greens71, fullgate72, then requests a fresh root queue for one20min RTMP soak and one retry. No recovery or Gate2 pass is claimed yet.
