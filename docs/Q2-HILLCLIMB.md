# Q2 quality climb

All three CPU/source receipt audits are complete. Execution is HELD. There is no new measured
baseline, arm result, quality ranking, winner, or closest measured near-miss.
The owner requires the models to prevent leaks before moderators react.

## Baseline identity

The coordinator worktree is
`/home/elan/.t3/worktrees/irl-shield/t3-3af688c7`, branch
`t3/q2-quality-hillclimb`. It started clean at `aa2b79e247e1f4ab3179c4f24663c4c05e40db2a`
and fast-forwarded with `git merge --ff-only` to
`65891cb0b515bc0c34ec4ded89aa6a3228992cc2`. The app branch is preserved and
locked. All three children were dispatched before coordinator edits.

The new baseline uses `bench/q2_hillclimb/baseline-policy.json`, byte-identical
to the historical frozen baseline policy. Configuration identity does not
make the historical measurement a new baseline. Coordinator metadata receipts
are in `out/q2-hillclimb/`:

| Receipt | Identity or purpose |
| --- | --- |
| `source-identity.json` | Exact current source and frozen harness hashes |
| `baseline-plan.json` | Literal unexecuted render/grade/aggregate argv for all 14 tune variants |
| `01-metadata-audit.log` | Metadata validation, no decoding or inference |
| `{precision,recall,temporal}-audit.json` | Read-back, patch and hash verification of all hand-backs |

The sealed input manifest remains read-only at
`/home/elan/code/irl-shield/.tmp/q/frozen-a8a06e3/inputs.json`.
Its SHA256 is `4db58cb96244791874447951b893af48f99b6bd165a59c46884a40a3c5226972`.
All 14 source/truth byte hashes matched that manifest. Validation read bytes
only, with no decoding, OCR, detector execution, or scene selection.
The configuration SHA256 is
`0c1ef57d668b52d549676d842d433ed72abe07218642b70104ddc65092d18002`.
Current pipeline fingerprint is
`fa992bd3cfe8fff022eaa131bcb0090cdc64c9440665ba9dfdf44725d509c283`.
Quality bundle helper SHA256 is
`846ad6dfa282eef71a6ee28a9f79cc00f39c167df6b6881d87fbef73096ef5ae`.

New baseline output is planned at `out/q2-base-65891cb/`. It does not exist yet.
The dedicated baseline Mac mirror is planned at
`/Users/elannash/code/irl-shield-q2-baseline-3af688c7`. It is unprovisioned.
The existing historical plan names actual bundles under
`/home/elan/code/irl-shield/out/q-base-a8a06e3-cache3-v3/`;
`out/frozen-a8a06e3/` does not exist. Historical bundles remain untouched.

## Ownership and state

The task links and full fences are recorded in
`bench/q2_hillclimb/dispatch.json`. Each child uses a separate T3 worktree,
Codex `gpt-6.1-sol`, XHIGH, priority, with a 20-invocation cap and no children.
The coordinator has 16 invocations; the aggregate cap is 76. Every failed,
rerun, render, grade, test, profile and gate counts. Retrieval is separate.

| Lane | Implementation fence | Readiness |
| --- | --- | --- |
| A precision | Render/masking, optional mask_precision, related tests, q2_precision | Synthetic source receipts accepted; union adapter unwired; full gate incomplete |
| B recall | ONNX adapter and necessary new derived static entries, q2_recall | Config/CPU receipts accepted; execution HELD; GPU-event seam missing |
| C temporal | Engine/motion, optional optical_tracking, related tests, q2_temporal | Synthetic source receipts accepted; flow/delay/live seams incomplete |
| Coordinator | New q2_hillclimb files, this document, LOG-q2-hillclimb | Baseline metadata and commands prepared |

The root's separate v2 lane owns all v2 assets, preparation, manifest and
canonical attribution. Root retains the live relay, egress, security, CLI and
audio paths. The coordinator applies no other writer's code. Opus reviews and
applies the separate patches. No commits, staging, pushes, or PRs are authorized.

## Launch receipts

Both barriers are still active. Root must relay PHONE_TEST_DONE/GPU_RELEASED
before any GPU, ORT, CUDA, NVENC work or active-queue submission. Root must also
relay `V2_FROZEN` with the exact manifest SHA before any arm result or screen
metric. Idle time, elapsed time and a stopped root runner grant no release.
The active EX performance queue has not been supplied. The coordinator needs
only root's freeze receipt and queue metadata, not v2 pixels or scene details.

V2 stays unread and unevaluated by all quality arms. Root owns its exactly-once
evaluation after the final frozen policy on Sunday November 1 at 06:00
America/Los_Angeles, which is **14:00 UTC** after DST ends. Saturday's v1 policy
freeze is October 31 at 06:00 PT, **13:00 UTC**. Coordinator hand-back cutoff is
Saturday **12:30 UTC**. Spent v1 may later be a separate `spent v1, dev only`
table. Its original manifest, policy, result and one-shot record stay intact.

## Screen order after release

Use the same frozen tune input SHA for every baseline and arm. First establish
a fresh 658 baseline. For each changed pipeline fingerprint, render a paired
baseline on that same branch with candidate behavior disabled. Config-only
recall arms retain the base fingerprint. Source equality alone does not prove
Mac runtime cache-signature equality. Record actual schema-3 judge signatures
and compare them before accepting any comparison. Never regrade a historical
bundle under changed source or bypass identity checks.

1. Precision has first priority. Read the actual renderer and sealed giant
   audit. The renderer already fills convex quads and pads by the shorter edge
   height with a 3px floor. Test padding reduction only around the complete
   detected polygons. Preserve all 13 positive closeups, especially house 11.
   If the bare-quad union exceeds the bound, report the guard failure. Discarding
   quads, trimming text ink or switching to blanket protection cannot fix it.
2. Screen the five separate recall knobs using licensed tune counterexamples,
   starting with both Mazatlan variants and mandatory synthetic positives.
   The prepared knobs are Small960 to1280, Medium960, detector threshold .2,
   box threshold .4, and accurate8Hz. Both threshold options affect both lanes.
3. Screen tracking independently of delay. Require valid forward/backward
   optical flow within D and generation-safe, fail-closed motion paths.
   D1/D2/D3 are a separate diagnostic sweep. Report any coupled A change as
   `A=floor(D*fps)` and its actual value. D>1 cannot be adopted.
4. Stop a screen on a counterexample and keep its rejection in the ledger.
   A screen pass establishes no all-seven conclusion. Surviving policies need
   all seven tune clips, 14 variants, sealed masks and a full scorecard.
5. Stack winners only after separate quality and performance passes, then
   rerun the stacked policy and same-branch baseline. No stack is prepared yet.

The source diagnosis behind this order is read-only
`/home/elan/.t3/worktrees/irl-shield/t3-4fb60399/docs/Q-GIANT-AUDIT.md`.
Its historical raw giants and smaller-receipt union floor prevent an inference
that rectangle replacement or a raw-giant filter alone solves the area guard.
These are historical findings, not new Q2 measurements.

## Qualification receipts

Existing scorers, judges, family registry, area validator, cache signatures and
source checks are frozen. Detector families come from the actual model registry.
Input truth uses Tesseract eng and Vision accurate en-US independently of the
PP detector. Output leakage includes all three judges, including PP-v5 English.
Natural hidden fraction must reach .90, synthetic through-interval hidden
fraction 1.00, real-video guards must pass, median mask area must be at most .15
with the existing `validate_area_ceiling` basis receipt, and **each** clip must
have protected fraction strictly below .02. The basis remains
`bench/gate-1-policy.json`; its bytes remain unchanged.

Each candidate also needs actual GPU time per source frame on the 1080 Ti at
30fps while NVENC runs, sustained fps, and p95 added latency. Timed trials need
at least 30 steady seconds after warmup, with medians from at least five cost
repetitions where appropriate. Report CPU preprocessing, motion and rendering
cost separately. CUDA events must surround actual ORT work on a known user
stream or come from verifiable device profiling. Record actual detector calls,
steady source-frame denominator, transfer/copy stream inclusion, waits, active
provider/static-model identity, GPU identity and raw event/profile receipts.
Host-wall detector durations do not establish GPU time.

The current ONNX constructor exposes no known user stream through its public
construction path. The recall plan has `gpu_event_argv: null`, so it cannot earn
promotion. Its clocked argv can later establish sustained delivery and p95
latency, not GPU event cost. No `nsys` executable was found on the local PATH.
A verified profiling path or an authorized opt-in construction seam is still
needed. No timing-only source edit may silently invalidate baseline identity.

Every GPU job must serialize through root's supplied EX queue with start,
during and end readiness, memory/load and `other_busy-v2` receipts. Keep root
NVENC and the phone test separate. Untimed quality uses the existing SH lease;
never acquire that SH lease inside a timed job already holding EX. The prepared
quality argv uses the existing `quality_bundle` CLI and its canonical host lease.
The queue is not started, polled or populated by this work.

Mac judging uses a dedicated mirror, matching source/bundle identity, and the
persistent `bench.vision.Vision` helper. Use the existing SDK interpreter paths
in the prepared plan without resolving interpreter symlinks or Python overlays.
Source sync is one rsync script excluding `.git`, `.build`, `out`, `.tmp`, venvs,
caches and secrets; it performs no delete and does not target other mirrors.
Build the real helper in the dedicated mirror and record actual runtime cache
identity. No Mac commands have run in this coordinator task.

## Current limits

No arm has a new scorecard or a genuine GPU measurement. The best guard-passing
policy and closest measured near-miss are both null. The historical baseline
and rejected B12 are context only. See the ledger for separate historical and
current states.

Recall used 10/20 invocations during readiness. Its remaining 10 cannot cover
all fourteen renders plus fourteen grades and repeated timing as individual
commands, even for one arm. The prepared plan is an inventory, not authorization
to exceed a cap or disguise multiple trials as one invocation. Further work
must fit the remaining aggregate/per-lane budgets or receive root's revised
allocation before launch.

The full gate has not run in this coordinator worktree. This patch adds data
and documentation only. Child readiness tests do not qualify the production
pipeline, and the root must run the full gate after applying the selected code
and before any push/PR. Coordinator metadata checks exercise exact input,
policy, source, patch-content and artifact identity only.

## Completed receipt audit and remaining integration

Precision preserves the default Renderer and adds a keyword-only padding floor
plus an opt-in padding-budget adapter. Read logs show 23 affected synthetic
tests and 96 default byte comparisons. The adapter counts clipped raster union,
retains bare quads if they exceed its budget, and reports failure. It may render
14 times per LIVE frame. CPU cost and all 13 actual audit-positive ink coverage
remain unverified. Fixed padding .20/.10/.00 can use the current quality seam;
the union adapter cannot. `quality_bundle.py:227` omits the existing explicit
renderer argument, and no budget diagnostic is retained in sealed records.
The adapter is not integrated or ready for a valid union-budget scorecard.

Temporal adds image-corner forward/backward LK flow and a validated global
homography. Read logs show 28 focused CPU tests, five physical guard failures,
byte restoration and final green. This is not independent text-object tracking.
The engine carries generation tokens through its worker, but existing live
callers do not supply them. `offline_quality.py:129` constructs flow history
without its required horizon; `quality_bundle.py:227` exposes no motion adapter.
Flow sealed rendering is blocked before presentation. D2/D3 remain blocked by
existing offline and clocked D<=1 checks; no D>1 adoption or guard relaxation
is proposed. These necessary seams are outside the granted child/coordinator
write fences and are left untouched for root's integration work order.

Both tracked diffs match their fences, all supplied application/artifact hashes
match, and reverse-apply checks pass. The source fingerprints differ from the
coordinator baseline. Precision is
`b9bbc630e0ad2213bb5f16576fcba832141422cce97d5643f40ca62f4ea6037a`;
temporal is `f4d212faff6a2f750e4ed9e636a81d0f02b5252f8d2f3fdca903c11857abfdbe`.
Both need paired baselines on the final branch before comparisons. No child
source has been applied to this coordinator tree.

Precision attempted a full CPU gate with temporary synthetic video, stub
models/judges and temporary queues. It timed out at 240 seconds with no final
receipt. Its partial log has an existing forced-deadline queue-test failure.
The exact unchanged test passed alone, but the cause remains unresolved and
the full gate remains incomplete. Recall and temporal did not run a full gate.
None of these receipts earns a push or production qualification.

Before any timing launch, normalize the prepared plans to one production host
configuration. Precision and recall clocked argv request 720p; temporal names an
unprovisioned 1080p30 source. The owner specified the 1080Ti GPU at 30 fps, not a
license to compare different source resolutions. Every arm still lacks actual
verified GPU timing while NVENC runs.

Final readiness budget is 40/76 used, 36 remaining: coordinator 7/16,
precision 12/20, recall 10/20, temporal 11/20. No cap is expanded. All known owned
child test processes exited per their cleanup receipts. No child is pending,
and no running delegate was polled or restarted by this coordinator. The
requested interim readiness is complete; execution awaits root's release,
freeze receipt, queue metadata and exact integration scope.
