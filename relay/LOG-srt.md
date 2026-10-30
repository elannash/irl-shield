# SRT implementation ledger

## 2026-10-30 — CPU implementation and root-queue handoff

Assigned tree: `t3-1f59735b`, app branch `t3/srt-ingest-parity`.
Clean HEAD `aa2b79e247e1f4ab3179c4f24663c4c05e40db2a` fast-forwarded to exact
`65891cb0b515bc0c34ec4ded89aa6a3228992cc2`; tree locked. Nothing staged,
committed, pushed or submitted to a queue by this lane. No children used.

Skills: codebase-design, tdd, diagnosing-bugs; test-review gate reference and
research measurement rules read. This is Codex-authored implementation in the
assigned thread. No global configuration, secrets, Twitch, owner service process,
production data, Mac, detector, renderer, scorer, quality policy or egress-worker
change was made.

The initial packet held GPU until phone completion. The conductor explicitly
superseded that hold with SRT_GPU_RELEASED. GPU remains root canonical EX queue
only. CPU_SHORT_RELEASED authorized bounded synthetic checks under canonical SH,
nice 10, agents slice, native 2/OpenCV 1. No standalone GPU execution occurred.

### Findings and evidence

- Historical evidence read at `t3-ae860af9/relay/M2-HANDBACK.md:281–291`.
  Retained exact-remux receipt `/tmp/agents/irl-shield/m2-relay/59-capture-dts-repro.json`
  substitutes the failed DTS sequence onto archive payloads. It proves Matroska
  rejection at 83,970→83,229/90,000; it does not prove those were the main reader's
  packets or identify their origin. No exact historical RTP payload was supplied.
- `b508d462` already fixed non-full EOF DROP/old-media ordering. Its real TCP/NUT
  tests remain green (`out/srt/21-input-eof-regression.log`). This is a separate
  previously fixed bug, not an attribution of the historical SRT latch.
- A current real MPEG-TS/TCP clock reset decoded as a large forward wrap jump
  without generation invalidation. Red: `06-ts-wrap-generation-red.log`; green:
  `07-ts-wrap-generation-green.log`. The final affected run includes the same
  discontinuity case. `NetworkInput` now preserves display PTS, reports packet
  reordering and decoded timestamp anomalies, and invalidates/reanchors a decoded
  video discontinuity without relaxing the existing generation floor.
- Current real SRT hard kill → one-shot replacement reproduces publisher failure
  and persistent transport HOLD. `17-real-srt-replacement-diagnostic.log` shows
  `publisher-collision`, 14 messages then publisher exit, and no newer decoded
  generation. It also records a small packet-DTS regression while main decode
  continues producing LIVE. This is a current equivalent of the historical
  failed-publisher pattern; attribution of the old run remains an inference.
- The byte-preserving replay sender retries connection failures without changing
  MediaMTX's publisher ownership policy. Green `18-real-srt-replacement-retry-green.log`
  returns LIVE in generation 9 after generation 5. Final affected run
  `23-srt-final-affected.log` returns LIVE in generation 7 after generation 3,
  preserves the moderator HOLD across reconnect, then releases it explicitly.
  That final run reports two packet-DTS regressions and seven mapped video drops;
  no decoder failure is inferred from those counters.
- Old independent SRT capture ends after the first disconnect:
  `09-capture-reconnect-red-isolated-publisher.log`. New raw-TS capture reconnects;
  first/last connection segments independently decode video and audio. Green:
  `10-capture-reconnect-green.log`, repeated in final affected run 23.

### Execution accounting

`out/srt/invocations.jsonl` is append-only. Every attempted test/probe/validation
call consumes the 36-call budget, including failed launch/lease attempts. Read-only
retrieval and source/artifact writes are separate. The final handback records the
current total and remaining reserved queue work.

1 failed scope launch lacked session-bus variables; no test started. 2–5 refined
the TS reset reproduction (including one failed edit command, whose unchanged
fixture was tested again). 6 is the generation red; 7 green. 8 exposed same-process
libsrt startup rejection in the harness; publisher isolation corrected that.
9 capture red, 10 green. 11 hung in test cleanup after killing a process inside a
multiprocessing Event wait; only that test and its MediaMTX child were terminated.
Cleanup now avoids setting the killed child's Event; later short checks have a
55-second process-group timeout. 12–15 exposed overly short delay/loop and then
the failed replacement; 16 was rejected by a racing EX lease before test startup.
17 confirms publisher collision; 18 retry/reconnect green. 19 verifies/copies the
pinned MIT MediaMTX tool; 20 all three SRT tests green. 21 existing EOF tests green;
22 CPU tooling/fixture A/V probe green; 23 final three SRT tests green. 24 records
an earlier empty `git diff --check` result retrospectively. Later verification
entries are authoritative in the invocation ledger.

### Pending acceptance

Root must provide the SRT queue session and run the exact packet in
`out/srt/timed-jobs.json`: long unified Linux gate, GPU smoke, then one 20-minute
SRT soak. At most one contended soak retry; no blind deterministic failure retry.
The wrapper preserves the inherited queue FD and caps physical soak executions.
Root's forced/contended receipt is authoritative; no uncontended timing claim.

The CPU fixture probe (`out/srt/cpu-probe.json`) measured source-only median A/V
0.083333 ms from two decoded flash/tone pairs. It is **not network or production
A/V evidence**. The timed harness writes independent network flash/tone offsets,
checks requested duration/frame count/PTS continuity, protects the scheduled HOLD
and accurate-lane stall, and requires LIVE in the final ten seconds. This harness
has not yet had its root-queued smoke or soak.

The real Moblin MPEG-TS path/hash has not been supplied. It remains the primary
private diagnostic when supplied; no sample or scenes were invented. No attended
Moblin SRT session occurred. Owner attendance remains necessary. No new privacy,
quality, OCR, trusted-seal or bench score claim is made; the required stream-path
bench rerun is pending root scheduling.

SRTLA remains report-only and unbuilt. Official-source access for compatibility,
license/source and install requirements is pending the conductor's answer to the
packet's public-network restriction. No unknown license is represented as free.

Task-specific invocation, tool-copy and probe helpers are retained under ignored
`out/srt/`; their dated/machine-local code is excluded from the source patch.
The portable `scripts/m2-srt-soak` entry point remains in the patch.

Final preparation update: probe25 passed. Invocation26 was cancelled while its
owned host-lock process waited for canonical SH; no package test or validation
started. The final source adds explicit native thread caps to capture-test decode
and keeps its scratch under `/tmp/agents/irl-shield/srt-tests`. Owner-fixture mode
now performs independent decoded-video/audio continuity checks even when A/V
markers are unavailable. Final compile/capture rerun and patch reverse-check remain
pending the root slot. Invocation27 writes the complete review patch and hashes;
it does not run functional tests. These pending checks are explicit in handback.

## 2026-10-30 — Authorized official-source SRTLA research

The conductor authorized read-only official GitHub/docs/license research,
superseding the research-access restriction only. Runtime public networking,
publishing, accounts, upload, install, build and listeners remain prohibited.
The research skill's primary-source/evidence contract was applied; no children.

Pinned SRTLA revision37862da3d0c13b46956efd3f88877053293d97d6 and patched SRT
revision4b6e11be7d2090a3c982c71903b56ed748075e9a; MediaMTX source atv1.21.3.
All primary-source URLs, access timestamps and snapshot hashes are retained in
`out/srt/research/sources.json`. Source reads are retrieval, separate from the
36-call execution budget. Failed API/raw-path retrievals are not runtime tests.

SRTLA report is now complete in `docs/SRT.md`: AGPL-3.0-or-later receiver,
MPL-2.0 optional patched SRT, MIT MediaMTX; unsupported public receiver status;
source-inferred streamid preservation; Go gosrt backend mismatch with C++ tuning
guidance; Linux build prerequisites; and an actual deployment blocker: the
receiver binds INADDR_ANY without an explicit-address CLI option. No build or
compatibility claim follows from source inspection. Full runtime acceptance
remains pending the previously identified gate/queue/Moblin work.

Invocation28 refreshes review artifacts after this documentation-only change.
No functional test, GPU job or stream runs in this update.

## 2026-10-30 — Final source freeze checks

Conductor issued CPU_SHORT_RELEASED for final source compilation and capture
regression only. The full Linux gate remains root-owned SH functional-CI work;
it must never be scheduled under EX because nested SH checks would deadlock.
The SRT gate EX entry was retired, never submitted by this lane. GPU smoke/soak
remain EX-only, with no lane submission or queue polling.

The ledger retains every prior event, including authorized SRTLA report refresh
28. One bounded SH invocation now runs final source checks and refreshes proof.
Its receipt and source-freeze status in handback determine the outcome; no
long gate, GPU run or Moblin session is performed here.

Final source check invocation29 passed: eight Python files compiled; portable
launcher bash syntax passed; real reconnecting SRT capture regression passed
with explicit native thread caps and owned scratch. Complete patch reverse-check
and whitespace checks passed. FINAL_SOURCE_FROZEN; runtime acceptance remains
pending root SH full gate, EX GPU smoke/soak and Moblin evidence.
