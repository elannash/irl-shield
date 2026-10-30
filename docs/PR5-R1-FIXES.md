# PR5 round-1 implementation

Base: `fa0d159494137abb0164ff49b8960b5164547a19`. This is an uncommitted patch
for Opus to apply and review. No engine, renderer, detector, scoring or Q-policy
changes. No dependency, model or dataset installs. All new test media is generated
synthetic CC0; no third-party labels, logos or music.

## Transport and operational fixes

- The relay loop hands engine output to one writer thread through a replaceable
  one-frame slot. Ingest keeps draining while native egress blocks. Slow/failed
  writes discard the slot; fresh results are required afterward. Both the session
  and actual native handoff check current HOLD. Already encoding frames cannot
  be retroactively changed. Egress indices may skip but cannot replay.
- Recovery retries grow from 0.5 to 8 seconds, with 0–20% positive jitter. A
  continuous outage gets at least 60 seconds and five failures before termination;
  network-ready ACK resets that episode. OBS and Twitch still share one mux worker
  and its failures. Destination isolation is deferred and is not claimed.
- `shield run` writes no archive, frame log or runtime JSON by default.
  `--archive <dir>` opts into full evidence. A 128 MiB free-space reserve is
  checked before every evidence write; low disk or I/O failure disables evidence
  without stopping transport. Evidence can be partial. The encoder's required
  startup fragment is memory-only, capped at 1 MiB and discarded after headers
  are copied; startup packet retention remains capped at 16.
- Bind addresses must come from `--host` or `SHIELD_BIND_HOST`: IPv4 loopback or
  `100.64.0.0/10`. No owner IP remains in validators/defaults. Doctor reports the
  detected Tailscale IPv4 address or `unavailable`. No Tailscale config changes.
- Runtime and relay docs now describe the actual memory-only key route and
  bandwidth-test-only authorization. `TwitchStub` became `TwitchDestination` and
  its unused `connected` state was removed; all live callers were migrated.
- A configured synthetic key with no opt-in never even forms a Twitch URL.
  Explicit bandwidth-test routing remains covered; no live override exists.
- The pinned Linux PyAV 16.0.1 SDK enumerated both RTMPS and TLS output protocols
  (libavformat 62.3.100). Twitch URLs now use
  `rtmps://live.twitch.tv:443/app/…?bandwidthtest=true`. This is SDK capability,
  not a successful external Twitch connection. Twitch's public
  [broadcast guide](https://dev.twitch.tv/docs/video-broadcast/) describes the
  bandwidth-test query; its [ingest catalog](https://ingest.twitch.tv/ingests)
  publishes secure RTMPS templates. No Twitch publish/request with credentials ran.

## Mostly-slate diagnosis and amended native harness

The sealed fa0 result remains **failed**. Its verified source rows contain 938
encoded frames: 566 HOLD, 333 PROTECT, 39 LIVE. Coverage is independently recorded
as 884 `ingest-gap`, 54 `covered`; those counts overlap HOLD and do not identify a
unique hold source. Replaying recorded callback activity at presentation time
counts chat on 61 frames, Shield Mode on 1, manual/local on 154, and connection
and reconciliation on zero encoded frames. The remaining 350 HOLD frames have
no recorded active callback source and are transport candidates, not individually
proven transport-source attribution. There are no recorded overlaps between
scripted callback sources at these presentation instants. Transport hold changes
were not logged by the old harness, so exact per-source attribution is unavailable.

All 71 `session.disconnections` are ingest-reader drop notifications by the
runtime's dispatch code. They are not EventSub session or MediaMTX publisher
counts. The reader initiated the reconnects, but only its last failure code was
retained: generation 71, missing video timestamp. There were two missing timestamps;
reasons for the other generations are unrecorded. Deliberate publisher stop/start
is in the harness, but the old evidence cannot classify all 71 as deliberate,
queue overflow, or missing-publisher retries. No such history was invented.
New input summaries retain aggregate failure-code counts and the latest 64
reader drop events, including initiator; they remain memory-only by default.

Two concrete causes were addressed:

1. The synthetic sender generated only 105 frames across 8.952 seconds and 269
   across 20.409 seconds, while advancing PTS at a nominal 30fps. It drifted
   behind the relay clock. This is a harness pacing defect; the fixture now
   precomputes its pattern and skips elapsed source slots after descheduling.
2. A full eight-item reader queue previously discarded the generation and
   reconnected even for a healthy decode burst. A real TCP/NUT reader regression
   reproduced this separately. The reader now replaces oldest queued media with
   fresh media, preserving the connection. A separate one-item coalescing control
   slot prevents media replacement from evicting an ingest-drop HOLD signal. Gaps remain honest and protected;
   audio gaps become silence. The separate six-second egress test proves the loop
   keeps draining real ingest during a destination stall.

The new native assertion requires at least **50% LIVE** outside scripted chat,
Shield Mode and manual hold intervals. The denominator is every encoded frame
whose encoder-completion timestamp has no active scripted source. Startup,
transport/reconcile holds, ingest gaps and automatic coverage protection all
remain in that denominator. A majority threshold rejects mostly-slate output
while allowing the fixture's four-second detector fault and source restart;
it is a synthetic functional floor, not a natural-privacy or cadence target.
The old presentation-time audit yields 39/722 outside scripted holds. The new
completion-time assertion calculates its own exact denominator in the receipt.
It has not been qualified by a new native E2E run in this lane.

For any observable hold, the harness checks the **first encoded frame at or after
BEGIN**, even if END already occurred: it must be HOLD with independently decoded
black pixels. Streaming holds retain the one-frame latency bound and no-LIVE
check during the active interval. Generation plus frame index identifies the
witness; archive and network timestamp/pixel associations must match, or fail.
Events after output shutdown are explicitly unobserved rather than passing.
The old 10.616 ms Shield pulse had no in-interval completion; its first following
frame was 241, HOLD at +14.680 ms. This diagnosis does not reclassify its old failure.

## Verification receipts and limits

`out/pr5-r1/invocations.jsonl` is append-only and includes failures, fixture
corrections, mutations, protocol enumeration, source audit and host gates.
`handback.json` records the final count, exact commands, source freeze and host
results. Raw logs, mutation diffs and byte-identical restoration hashes live
beside it. Behavioral reds include the six-second real-reader failure, retry
termination at 2.6 seconds, default archive and low-disk failures, bind/TLS
failures, real-reader burst reconnect, sub-frame witness selection, and deliberate
key-route/late-HOLD/first-frame-LIVE mutations.

The Linux and dedicated Mac `scripts/check` gates run only after source freeze,
with canonical SH leases, two native threads, OpenCV one and nice 10. Mac uses
only the pre-existing read-only unified SDK. No setup/check/requirements changes
or new installs were necessary. Tests requiring Linux MediaMTX retain their
explicit Mac platform skip. Native Twitch CLI is NOT RUN BY DESIGN when its
binary is unprovisioned, under the existing local-only verification boundary.

No full native E2E was run here. Its one remaining execution belongs to root,
after Opus applies/commits this patch and explicitly authorizes root's run.
No fresh gate-1 privacy, live-walk, SRT, real Twitch, natural-scene quality,
A/V-generation association or production-readiness qualification is claimed.
