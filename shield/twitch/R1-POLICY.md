# Round 1 event policy

This records the policy implemented by `events.py` for the four accepted event
findings in `pr2-triage-r1.json`. It covers the policy interface, not transport
recovery, authentication, model verification, or a live Twitch session.

## Connection identity and public interface

All state methods and the `generation`, `phase`, `session_id`, and `remembered`
properties acquire one `RLock`. A call from another thread waits through the
current hold callback. The lock is reentrant so a callback can report a fault or
revocation without deadlocking. The transport must still marshal socket calls
onto its owner loop and pass the generation captured for that connection; reading
the latest generation when handling an old callback would defeat the fence.

| Call | Contract |
| --- | --- |
| `connection_started()` | Increments the generation through `fault('connecting')`, invalidates session/query identity, asserts the connection hold, then enters `connecting` unless revoked or a reentrant fault invalidated that attempt. Returns that attempt's generation. |
| `welcome(session_id, *, generation)` | Returns `True` only for the current, nonrevoked `connecting` attempt and a nonempty string session. Marks the connection live and enters `subscribing`. Stale calls return `False`. An invalid session on an otherwise current attempt faults it. |
| `begin_reconcile(*, generation, session_id)` | Requires the matching live welcomed session and generation, in `subscribing`, `ready`, or `reconciling`. Otherwise returns `None`. Asserts connection and reconciliation holds and returns a new immutable `Reconciliation(generation, shield_revision, session_id)`. A callback fault can invalidate it before return. |
| `reconciliation_current(snapshot)` | Requires the exact current snapshot object, matching generation/session, live connection, nonrevoked state, and `reconciling` phase. Starting another query invalidates an earlier snapshot even in the same session. |
| `reconciled(active, snapshot)` | Requires a boolean status and a current snapshot. Applies Shield status only if no newer Shield event has changed its revision. Checks again after callbacks. Returns `True` only after completing the guarded release; stale or interrupted work returns `False`. |
| `fault(reason='disconnected', *, revoked=False)` | Increments and returns its generation, clears session/live/query identity, latches revocation if requested, enters `disconnected` or `revoked`, and asserts the connection hold. |
| `reconnect(url, *, generation)` | Requires current live `ready` state and an approved endpoint, then enters `handover`. Returns `False` for stale or unsafe calls. An unapproved URL on a current ready attempt faults it. |
| `handed_over(session_id, *, generation)` | Requires current live `handover` state and a nonempty string session. Replaces the session and returns to `ready` without changing the generation or releasing any hold. Returns a boolean. |
| `accept(envelope, *, generation)` | Validates metadata, subscription identity, broadcaster identity, and command authority before classifying a hold or release. Protective events work in every phase and with a stale generation. Releases require the current live ready generation and the replay/time/order checks below. |

There are no default generation arguments or retained compatibility methods.
`session_id` becomes `None` on fault. The constructor starts held in `connecting`
at generation zero; a transport connection attempt uses `connection_started()`.
An opaque snapshot must be returned unchanged; reconstructing its dataclass
fields does not produce a valid query token.

## Guarded release and callback reentry

Reconciliation holds two independent internal sources: `twitch-connection` and
`twitch-reconcile`. It first applies the Shield status, rechecks the snapshot,
releases `twitch-connection` while `twitch-reconcile` still holds, rechecks again,
sets `ready`, and finally releases `twitch-reconcile`.

The extra hold covers callbacks that reenter `fault()` **before** applying their
requested release to the underlying control. If the connection-release callback
faults and then clears the connection source, the reconciliation source remains
held. If the final reconciliation-release callback faults, the connection source
remains held. Neither case produces a LIVE transition after the observed fault.
A later valid reconciliation clears the internal sources. No internal release
clears `chat`, `shield_mode`, or `local` sources.

If the status callback accepts a Shield begin and then applies its older false
status, the changed Shield revision causes protection to be reasserted while the
internal guards remain held. Releases are inactive during reconciliation, so a
revision change during that callback can only require protection. A status read
started **after** an already accepted Shield begin remains authoritative if no
newer begin arrives during the query; reconciliation can recover a missed end.
Callbacks must implement the requested hold operation; callback exceptions
propagate rather than being relabeled as invalid network input.

## Timestamp admission and bounded replay

An authorized moderator/broadcaster chat hold or Shield Mode begin is never
rejected solely for its timestamp: future by 0.2 seconds, 10 seconds, or many
hours; before session start; older than the age floor; naive, missing, or malformed
timestamps all retain protection. Authentication and broadcaster checks still
apply. Shared-chat badges from a different origin channel do not authorize a
hold. An ID still in the bounded dedup cache returns `duplicate`.

A release requires an aware, parseable finite timestamp at or after policy start,
strictly above the permanent replay floor, no more than 30 seconds ahead of the
local wall clock, and strictly newer than its source's ordering time. The clock
floor advances to at least `now - max_age` (default ten minutes). Only the owner
can release a chat hold. Shield end releases only the Shield source. Equal
ordering timestamps favor protection.

The **30-second forward-skew allowance is a local engineering choice**, not an
attributed Twitch guarantee. This task did not make a live Twitch call or
establish Twitch guidance on a host clock tolerance. Larger discrepancies keep
releases closed while still admitting protection.

For protective events with an unusable/pre-start/expired timestamp, ordering
uses receipt time. Otherwise their ordering timestamp is clamped to no later
than receipt time. Per-source ordering never moves backward. Thus a far-future
begin cannot require waiting for that remote time before a valid later release.
Release timestamps retain their admitted remote time for replay/order checks.

The cache remains bounded by `capacity` (default 4096). Time expiration and
capacity eviction advance or respect a permanent floor. A protective event whose
ID has been evicted may conservatively reassert a hold, even with an old
timestamp. An expired release cannot become executable again: its original
stamp is at or below the permanent floor. This assumes redelivery preserves an
ID's original content and timestamp. Rewriting an old release with a fresh
stamp is outside the transport contract.

This changes the earlier `PROTOCOL.md` claims that all future timestamps are
rejected and all events at/below the floor are discarded: those statements now
apply only to releases, with the explicit 30-second forward allowance. It also
changes the old replay test's expected outcome for an evicted protective ID:
protection is reasserted instead of discarded. Ordinary or unauthorized ignored
messages no longer consume dedup entries; `remembered` counts admitted control
IDs, including admitted releases subsequently rejected by source ordering.

## Regression receipts and limits

Raw evidence is in `/tmp/agents/irl-shield/m3-r1-CHILD/`. Every invocation has an
exact `run-*.sh` command, a `.log`, and an `.exit` file. The pre-fix policy is
`events.before.py`; the old-interface regression suite is `test_events.red.py`.
The intermediate release/status regressions also have byte-for-byte policy and
test snapshots. Test invocations used: **6 of 6**.

| Invocation | Result and what it exercised |
| --- | --- |
| `run-01-red.sh` / `01-red.log` | Base policy, old interface: 11 tests, 28 assertion/subtest failures. Reproduces timestamp/phase hold loss, both welcome/fault orderings, callback-reentrant fault/revocation, and a real two-thread fault/status overlap. No signature/import failures. |
| `run-02-green.sh` / `02-green.log` | Migrated interface, 14 tests passing. Includes current/stale generation, session mismatch, overlapping query identity, release phase/time checks, and bounded replay. |
| `run-03-release-red.sh` / `03-release-red.log` | One regression fails: callback fault before connection-release effect leaves transition ledger `LIVE, HOLD`. Final state alone had missed that exposure. |
| `run-04-green.sh` / `04-green.log` | 15 tests passing with separate reconciliation guard; covers both release callback positions and both fault/revocation outcomes. |
| `run-05-status-red.sh` / `05-status-red.log` | One regression fails: Shield begin is accepted reentrantly, then older status False produces LIVE. |
| `run-06-final-green.sh` / `06-final-green.log` | Final 16 tests pass, including the callback Shield-begin correction, clock-ahead age expiry, and malformed-time authorization checks. |

The initial phase regression's reconciling/Shield-begin subcase started a second
query after delivering the event. Its final-state expectation was too strong:
a later authoritative false query may recover a missed end. The retained test
uses a matching true status for pre-query Shield begin; the existing
`test_reconciliation_release_preserves_newer_shield_chat_and_local_holds` and
callback regression exercise false status against a begin delivered during the
query. The substantive old-policy `inactive` failures remain in the red receipt.

All suites ran in the user systemd scope/slice requested by the packet, under
`MemoryMax=2G`, `CPUQuota=200%`, `nice -n10`, native thread limits of two, the
parent's read-only Python 3.11 runtime, and this checkout's cwd/PYTHONPATH. The
concurrency test creates exactly two executor workers and joins both. All six
owned scopes were checked inactive/dead after completion. A systemd scope's
`Result=success` does not replace the test process exit receipt: intentional red
runs have `.exit` value 1.

This is policy-unit evidence with synthetic data, not the full repo gate,
transport integration, a bench scorecard, TLC/Java evidence, or live Twitch
verification. The parent owns transport migration/integration and the model.
No Mac, GPU, credentials, login, external Twitch calls, staging, commit, push,
PR, or parent-checkout edits were performed.
