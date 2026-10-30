# R3: raw Twitch order and pending missing-stamp barriers

**Final bootstrap verification is incomplete: this worker's strict four-invocation
allowance is exhausted.** The final source-mapped model and public replay are
prepared, but neither has been executed against the final `0e90e43f` freeze.
No earlier pass is attributed to this final revision.
The final integration steer assigns the prepared replay to the parent's combined
functional-gate process after audit/copy. The already executed 703 replay still
counts here; that assignment does not recover a spent invocation. Final 0e90 TLC
is also blocked by the exhausted allowance.

The original R3 defect is reproduced on the actual `9cb8e812` policy. A raw
Shield begin **41**, received at local time **10**, is stored as policy key
**40**. An older raw end **40.5**, received at local time **11**, clears the
hold while the independent raw obligation remains true. Direct TLC reports
`AuthorizedShieldBeginPersists` at **state 17**. The actual old-policy public
replay observes LIVE; the superseded `70345615` candidate observes HOLD.
[Raw counterexample](evidence/r3/old-raw-fail.tlc.log),
[old configuration](evidence/r3/old-boundary.cfg),
[complete seventeen-state path](evidence/r3/old-raw-fail.mmd).

The `70345615` candidate passed bounded TLC with **13,022,861 generated states**,
**1,348,728 distinct states**, **zero queued states**, depth **41**, exit **0**.
Its combined old/fixed public replay also exited **0**. Those runs finished
before the subsequent pause/stronger-bootstrap messages arrived. That candidate
allowed the first fresh stamped release after an unseeded missing hold to clear
it; the conductor subsequently required a pending barrier instead. These passes
are therefore **superseded evidence**, preserved with their exact checked inputs:
[703 policy projection](evidence/r3/TwitchControl-70345615.tla.txt),
[703 configuration](evidence/r3/TwitchControl-70345615.cfg),
[checked environment](ControlEnvironment.tla),
[703 replay source](evidence/r3/public_replay-70345615.py.txt),
[703 TLC log](evidence/r3/fixed-raw-pass.tlc.log),
[703 public replay log](evidence/r3/public-replay.log).

## Final source and isolation

The first command was exactly `pwd; git branch --show-current; git rev-parse
HEAD; git status --short`. It returned isolated worktree
`/home/elan/.t3/worktrees/irl-shield/t3-39e664cc`, branch
`t3/r3-raw-timestamp-model`, exact requested HEAD
`9cb8e812af152833f97adc2ce1cdd4858c5efdf3`, empty status.
`git worktree list --porcelain` confirmed the parent has a different path.
No worktree or git index/history mutation was issued by this worker.
Writes are confined to `docs/model/` and owned scratch
`/tmp/agents/irl-shield/m3-r3-model/`.

| Input | SHA-256 |
| --- | --- |
| Actual old policy, `git show 9cb8e812:shield/twitch/events.py` | `aa359f9b70a580b768b755febea8433d77ff1402ee6c70771e1967348c92c082` |
| Superseded candidate actually checked | `70345615b503a0f8e03cbdf9da138cdac5f6bc055299d16223ae8692ba896807` |
| Final parent-frozen policy, mapped but not executed here | `0e90e43f52b3bd9444925469baf96b40d29480ecefd22c4eeb5afdd68bb630fd` |
| Transport snapshot read for mapping; parent will restore dial timeout separately | `c0267d0eac1ab7da3b4537b900b4037d53da4645a1e2abb735e5918001a3a426` |
| Public Control, unchanged at base | `806c51102caea5ba06985831412c89452fd0a000fd5b0343f1535cc5674b244d` |

The integrated implementation is in the **parent** checkout at
`/home/elan/.t3/worktrees/irl-shield/t3-3bb00dac/shield/twitch/events.py` and
`shield/twitch/transport.py`. This child's production files remain at the base
because its write fence is only `docs/model/`; that does not describe the
parent's integrated source as old. Parent files were read/copied, never edited.
Final snapshots are scratch `events-fixed.py` and `transport-final.py`;
the superseded candidate is scratch `events-70345615.py`.
The final steer retains policy `0e90e43f` but plans a transport-only restoration
of the upstream initial `_reset_timeout` before dialing. That timer is outside
this policy model. The parent must append its final transport hash and gate
receipt; `transport-final.py` is the mapped pre-restoration snapshot.
[Old hashes](evidence/r3/source-pre.sha256),
[final hashes](evidence/r3/source-fixed.sha256),
[final source diff](evidence/r3/frozen-source.diff),
[superseded diff](evidence/r3/frozen-source-70345615.diff).
[Final model/replay/tool hashes](evidence/r3/model-and-tool.sha256) identify the
unexecuted final artifacts; [checked 703 input hashes](evidence/r3/checked-703-inputs.sha256)
identify the exact archived inputs whose logs passed. The earlier
`model-and-tool-70345615.sha256` preserves their original historical path labels.

## Independent obligations and the final model

[BeforeR3Control.tla](BeforeR3Control.tla) extends the unchanged, checked R3
[ControlEnvironment.tla](ControlEnvironment.tla). It faithfully projects the
old policy's missing/pre-start/expired receipt fallback followed by
`max(started_at, min(at, receipt+30))`. It has no mutation flags.
The independent obligation retains every finite raw hold stamp, including
pre-start, expired and far-future stamps. It has **no capped exception and no
receipt fallback**. An old/equal raw release cannot discharge it.

The final [TwitchControl.tla](TwitchControl.tla) instead extends
[BootstrapEnvironment.tla](BootstrapEnvironment.tla). These are prepared,
**unexecuted** final artifacts. Policy and independent environment each maintain
their own raw high-water data; neither independent discharge nor its barrier
comes from a policy timestamp or output. The environment records raw stamp,
local receipt, prior raw high water, and a separate first bootstrap stamp.
A finite hold's raw evidence is retained when Helix adds another obligation.

For a missing/unparseable/naive hold with known prior high water, the barrier is
that prior raw high water, and only a strictly greater fresh release can clear.
With no prior stamp, `MissingPending` keeps the source held. The first valid
observation anchors it before that message can release anything; a first release
therefore ties its newly anchored barrier and stays HOLD. A later greater fresh
release can clear. `ObserveTimestamp` can occur in any phase, including before
welcome/subscriptions. Later observations update global evidence without moving
an already established source barrier. A rejected future release still advances
the global watermark, but cannot move an established held source barrier.

Helix active status creates its own independently recorded missing-stamp Shield
obligation in `StartCompletion`, when snapshot revision is current, **before**
`ApplyStatus` enters the public hold callback. The separate evidence preserves a
previous delivered raw hold rather than overwriting it. One bounded external
Shield activation permits a truthful active Helix read without a begin event.

The six invariant formulas are byte-identical to the pre-R3 versions:

| Invariant | Meaning |
| --- | --- |
| `NoLIVEWithoutCurrentChannel` | LIVE requires actual live socket/session, all three enabled subscriptions, and matching policy session. |
| `AuthorizedChatHoldPersists` | Independently recorded chat obligation forces HOLD. |
| `AuthorizedShieldBeginPersists` | Independently recorded Shield obligation forces HOLD; final model also records active Helix evidence. |
| `RevokedStaysHeld` | Revocation forces HOLD. |
| `LocalHoldPersists` | Local hold forces HOLD. |
| `NoLIVEWithoutCoverage` | LIVE requires coverage. |

No invariant was weakened or removed. The final model does not have a final TLC
receipt; its safety and even TLC parseability remain unverified within this cap.

## Mapping to the final frozen implementation

Policy line references below are to final `0e90e43f`; transport references are to
mapped snapshot `c0267d0e`. Both hashes were independently verified after copying.

| Model operation | Source mapping and limit |
| --- | --- |
| `InitialPolicy`, `PolicyFault`, `NewConnection`, `Welcome` | Policy 44–62, 114–130, 212–220. Source uses `-math.inf`; model zero is below every legal bounded raw stamp. Pending is separate from that sentinel. |
| `ObserveTimestamp`, `ObservedPolicy`, `Anchor`, `MissingPending` | Policy public `observe_timestamp`, 84–102: finite aware parsing, global max, and pending `None` anchoring before dispatch/release. Model policy flags represent source time `None`; independent bootstrap evidence is separately recorded. |
| `OrderTime`, `DeliverHold` | Policy `_protective_order`, 104–109; `accept`, 222–299. Raw finite stamps retain remote order. Missing order uses prior watermark or pending, never receipt. Existing per-source order uses max. |
| `ReleaseAdmitted`, `ReleaseReceived` | Policy 263–295: generation/live/ready/revocation, start/floor freshness, future +30 rejection, strict source order and equal protection. The model represents future rejection by state only; logging is parent-tested. |
| `BeginReconcile`, `Current`, token identity | Policy 156–169, 206–210. Distinct query indices represent object identity even with equal snapshot fields. |
| `StartCompletion`, status microsteps and repair | Policy 171–204. Active status latches missing Shield order at 175–177 before callback 178. Revision repair and current-token checks remain; separate connection and guard callbacks are retained. |
| Trusted metadata observation before dispatch | Transport `_task_receive`, 254–290, particularly 284. Public policy observation is modeled; socket execution and owner scheduling are source-mapped assumptions. |
| Planned handover metadata | Transport `_handover`, 204–223, particularly 217, separately consumes and observes candidate welcome before migration. `ObserveTimestamp` is available during handover. |
| Planned reconnect and handover | Policy 132–154. Session/subscription migration remains atomic by assumption. |
| `Output` | Base public Control, `shield/control.py:31–52`: named holds precede coverage. OCR/rendering are not checked. |

`accept` rejects invalid broadcaster/subscription envelopes before observing
their timestamps (policy 224–238). **Transport separately observes authenticated
socket metadata before notification envelope dispatch.** The invalid-envelope
replay calls public `accept` directly; it does not prove exclusion after a caller
has independently passed metadata to `observe_timestamp`. The model treats
metadata observations as trusted socket input, not authorization of an envelope.

## Bounds, retained schedules and omissions

All numeric model timestamps are scaled by ten, so 410/405 at local 100/110
represent raw 41/40.5 received at 10/11. `StartedAt=10` represents start 1,
`ForwardSkew=300` represents +30 seconds, and `ClockTick=10` represents one
second. The direct old config has `MaxGeneration=1`, `MaxQueries=1`, holds
`{410}`, releases `{405}`, no ordinary observations, and `MaxAge=6000` (600 sec).

The 703 checked config and final prepared config use `MaxGeneration=3`,
`MaxQueries=2`, holds `{Missing,5,20,410}`, releases `{405,410,411}`,
observations `{410}`, and `MaxHolds=1`. This deliberately reduces R2's potentially
14-million-state graph: **one delivered notification hold total**, with either
source and any known origin, rather than one per source. Missing-first and
known-watermark cases are present. Numeric 5 is pre-start; 20 is after start but
expired under the explicitly reduced `MaxAge=50` (5 sec). That parameter is a
supported policy constructor bound, not a changed production default. Replay
uses the real default 600 seconds and explicitly expired raw -1000.

The final model separately permits up to two active Helix status observations
through its two query identities; they do not consume `MaxHolds`. Its one
external Shield activation is bounded by `truthRaised`. The checked 703 graph
did not have these final bootstrap/Helix/metadata actions.

All preexisting lifecycle actions remain: queued welcomes, each enabled topic,
fault/revocation, unplanned new connection, stale/current welcome handling,
begin/read identity, completion microsteps/rechecks/repair, separate connection
and guard callbacks, planned reconnect/migration, local and coverage changes,
status failure and idle. Hold admission can occur during callback microsteps.
Observation may occur during any modeled phase. Releases remain serialized,
ready/current and only at the second receipt clock. There are no VIEW, SYMMETRY,
state/action constraints or post-violation invariant removals.

Explicit limits:

- Clock has two monotonic receipt values (10 and 11); notification holds arrive
  only at 10 and releases only at 11. Arbitrary skew, backward jumps, non-finite
  local clocks, repeated notification holds, release callback reentry and
  unbounded lifetime are excluded. For held raw 41, a strictly newer release
  does not fit the bounded local +30 window at receipt 11; the public replay
  advances receipt enough to check immediate release once fresh.
- Start and age floor are represented, with start minus one model unit replacing
  the source's tiny epsilon; no selected numeric stamp falls between those
  representations. Cache eviction, ID reuse/deduplication, capacity-induced
  permanent floors, and actual GC behavior are omitted. Replay has unique IDs
  and capacity 4096; receipt cache timestamps are not source-order evidence.
- Valid authorized notification parsing and source mapping are assumptions in
  TLC. Missing combines missing/unparseable/naive; finite numeric ordering does
  not model float-resolution collisions or date range errors.
- The model's ready release action does not deliver stale-generation/inactive
  releases. The real observer still sees their stamps first. Separate metadata
  observation overapproximates such timestamp arrival but does not execute their
  complete transport schedules. Parser/error paths and logger output are not
  proved by TLC.
- Socket fault detection and policy fault occur together. Half-open loss,
  watchdog latency/death, connect deadlines, OAuth, HTTP/subscription response
  validation and transport concurrency are omitted. Enabled subscriptions and
  atomic planned migration are environment assumptions.
- Helix truth is truthful when queried. Final model permits one unnotified
  activation; arbitrary external deactivation, stale status caches and arbitrary
  concurrent server changes remain excluded. Pending status ordering is modeled
  but unexecuted. Guard structural precedence is not a media privacy proof.
- RLock/owner serialization is a source mapping. Begin's hold assertions remain
  atomic. Arbitrary recursive lifecycle reentry/callback exceptions are omitted.
- No fairness/progress property is checked. Idle/status-failure stuttering avoids
  terminal deadlock; deadlock success is not availability evidence. No live
  Twitch, Mac, GPU, media path, OCR or visual acceptance check was run.

## Public replay and exact evidence scope

The executed [703 replay](evidence/r3/public_replay-70345615.py.txt) loads actual,
hash-pinned old/candidate policies and public Control by file path. It uses no
private fields, internal test helpers, source mutation or production seam.
It prints all seventeen states of the direct old trace, with raw 41/40.5 and
local receipt 10/11. Queue/subscription facts are caller-owned environment;
states 9/11 are source-mapped microsteps inside one public `reconciled(True)`
call. States 10/12/13/14 are observed through its public hold callback. The
policy replay does not open sockets or claim transport execution.

The executed tables use fresh instances per source, skew and older/equal case:
chat and Shield at +29.9, +30, +30.001, +31 (raw 41), +41 and +100000. Older/equal
stay HOLD at/below the old clamp boundary and expose old LIVE above it; the
703 candidate rejects them all. Every ordering case immediately follows with a
strictly newer successful release, already within the release freshness window.
Other executed cases cover missing/malformed/naive first holds, finite pre-start
and expired holds, known global high water from ignored ordinary chat and cross
source holds/releases, future-release isolation, and direct invalid-envelope
exclusion. The old negative control is the historical source, not a mutation.
A zero harness exit means the expected old violation and candidate safety were
both observed, not that the old policy passed safety.

The final prepared [public_replay.py](evidence/r3/public_replay.py) is pinned to
`0e90e43f` and is **not run**. It replaces the unseeded missing-first expectation
with first-release anchoring and later-greater success; it also adds public
`observe_timestamp` checks for welcome/keepalive/reconnect and candidate-handover
welcome, plus seeded/unseeded public `reconciled(True)` holds. These are policy
API replays; parent owns actual websocket tests and production regressions.

Test-gate rationale: output ordering belongs to public policy/Control boundaries.
The actual old source is the realistic negative control. Parent production/tests
are outside this worker's fence. The replay is the closest authorized executable
check and introduces no test-only export/flag/reset hook. Final changes lack a
new executable receipt because the cap is exhausted, not because a weaker
expectation was substituted.

## Four invocations, licenses and cleanup

| Invocation | Receipt |
| --- | --- |
| 1. Old TLC with negative initial barrier literal | Exit 255, config parser failure at line 13; no explored graph. This counts. [Exact invalid config](evidence/r3/old-boundary.config-error.cfg), [raw log](evidence/r3/old-boundary.tlc.log). |
| 2. Actual old clamp, corrected finite positive domain | Exit 12; `AuthorizedShieldBeginPersists`, state 17; 6,743 generated / 688 distinct / 44 queued; stopped at violation. |
| 3. Frozen 703 candidate TLC | Exit 0; six invariants; 13,022,861 generated / 1,348,728 distinct / zero queued; depth 41; 37 seconds. Superseded. |
| 4. Actual old/703 public replay | Exit 0; old RED/candidate GREEN, as scoped above. Superseded. |

**Actual invocation count: 4/4. No final 0e90 TLC, replay, parser check or test
suite was run.** Parent's later permission was explicitly conditional on the
remaining four-run allowance, which was zero. Its reported six parent runs and
planned seventh must be reconciled by the parent with this worker's four; this
report does not infer a final concurrent aggregate. No extra check was launched
on the assumption that the earlier pause restored budget.
[Ledger](evidence/r3/invocations.log), [exact commands](evidence/r3/commands.sh),
[exact TLC wrapper used](evidence/r3/run-tlc-70345615.sh.txt),
[Python resource wrapper](evidence/r3/run-public-replay.sh).

Every TLC/Python invocation used `systemd-run --user --scope`, agents slice,
`MemoryMax=2G`, `CPUQuota=200%`, `nice -n 10`; TLC used existing read-only Java/TLC,
`-Xmx1g`, `-XX:ActiveProcessorCount=2`, two native workers, `-fp 0 -lncheck final`.
[Live scope receipt](evidence/r3/fixed-scope-limits.txt) confirms slice, 2 GiB and
two CPUs. A separate first read-only scope-property query failed for absent
user-bus variables; setting the documented bus address fixed that read. It did
not run TLC/Python or consume a test invocation.

The checked graph uses TLC fingerprints; generated states include duplicates.
703 collision estimates are `8.5E-7` optimistic and `6.1E-7` from actual
fingerprints, not probabilities of implementation correctness. Neither estimate
applies to the unexecuted final model.

All new model/replay code is original work in this authorized Codex lane. No
SDK, model, dataset or asset was added. The existing TLC JAR's root MIT license
was byte-compared to preserved [TLC-MIT-LICENSE.txt](evidence/r2/TLC-MIT-LICENSE.txt);
its bundled EPL 2.0/GPL notices remain in
[the existing dependency notice](historical/evidence/TLC-LICENSE.txt).
Temurin 25 is GPL v2 with Classpath Exception, recorded in installed
`/home/elan/.local/share/mise/installs/java/temurin-25/legal/java.base/LICENSE`.
System Python's PSF license chain is `/usr/share/doc/python3/copyright`.
Tool binaries were not changed or redistributed.

[Cleanup receipt](evidence/r3/process-cleanup.txt) shows owned JVM PIDs
3538773, 3539254 and 3544738 exited, and all four owned scopes are inactive/unloaded.
All foreground commands returned. No process is handed off. No network, install,
scaffolder, secrets, environment dump, Mac, GPU, production/test/global edit,
worktree mutation, staging, commit, push, PR, merge or child agent was used.
Scratch source snapshots and TLC state data remain for the parent audit.
New files are deliberately untracked because staging was forbidden;
[tracking receipt](evidence/r3/tracked-base-files.txt) identifies edited base files.

## Historical preservation and unfinished work

R2 logs, configs, scripts and earlier historical evidence are untouched. The
unaltered pre-R3 report/environment/projection/config are archived under
`evidence/r3/*-before-r3.*`; their cap exception is historical and no longer the
raw-order contract. Earlier modules/configurations require their matching
archived environment, not whichever environment is current at the root.
The manual [Mermaid path](evidence/r3/old-raw-fail.mmd) retains all seventeen
states of the actual direct old counterexample and hides all off-path transitions
and all outcomes after the first violation. It is not a full generated graph.

Unfinished: final bootstrap TLC requires an explicitly available budget; the
final public replay is pending the parent's audit/copy and combined gate process.
Parent owns those receipts, the final transport timer hash, the full gate and
any larger-budget decision. Current four-run allowance grants no further run.
The latest parent arithmetic must retain all four worker invocations, including
the superseded public replay; no run is retroactively removed. Prepared wrappers perform one invocation per
call and no automatic retry; a new approved run must use a fresh scratch name.
The old original raw-clamp counterexample remains reproducible with
`bash docs/model/evidence/r3/run-tlc.sh NEW_OLD BeforeR3Control ABS_OLD_CFG`.
Final candidate recipe is the same wrapper with `TwitchControl` and the final
config, followed by the public replay wrapper, **only after budget authorization**.
