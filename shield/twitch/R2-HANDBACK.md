# PR #2 R2 implementation hand-back

Historical receipt, committed by the conductor as `9cb8e81`.
[R3-HANDBACK.md](R3-HANDBACK.md) supersedes the bounded hold clamp, missing-stamp
receipt fallback and capped model-obligation claims after round 3 review.

**Ready for conductor round 3:** all three accepted R2 findings have old-code
RED and fixed GREEN evidence. The final combined gate exited 0: **149 tests
ran in 76.938 seconds, 148 passed, one expected macOS-only skip**, including
**50/50 M3 tests**. Review budget: **33/38 invocations used**, five unused.
The fixed model passed six invariants over **14,747,184 distinct states**.

Implementation base `ea004ecdad9583996d4907cfb0f35ca130a227af`, actual/requested branch
`elannash/m3-twitch`, same assigned dedicated worktree. The conductor applied
test-only queue correction `9c86a70791c4af5e35aab042d6f3f7c2fd114280` on top.
That is the hand-back HEAD. M3 changes remain uncommitted and unstaged. The
model audit and final combined gate run 07 are complete.

| Finding | Red receipt | Current result |
| --- | --- | --- |
| `forward-skew-lets-stale-release-clobber-hold` | `01-policy-red.log`: unchanged base policy, two tests and six assertion/subtest failures; older chat/Shield releases accepted at forward skew 10 and 29 seconds. | `02-policy-green.log`: all 17 policy tests pass. Holds and releases retain Twitch order inside the common 30-second allowance. Older/equal releases return `expired`; a valid newer release works. Extreme-future ordering is bounded and never auto-clears a hold. |
| `model-release-obligation-uses-policy-order-key` | Direct TLC on a faithful `ea004ec` projection, no mutation flags: `AuthorizedShieldBeginPersists` fails at state 17. Hold Twitch 20/receipt 10 remains an independent obligation after older end Twitch 19/receipt 11 is admitted and reaches LIVE. | Fixed TLC passes the six unchanged invariants: 150,289,557 generated / 14,747,184 distinct / 0 queued states, depth 44. Actual old/fixed public Python replay confirms old RED/fixed `expired` + HOLD and successful newer releases. Parent audited and integrated the owned files; R1 counts remain historical. |
| `start-never-settles-after-startup-revocation` | `03-startup-red.log`: unchanged base transport, all three routes leave `start()` pending: validation 401 during subscription, validation 401 before reconciliation, and EventSub revocation during reconciliation. | `04-transport-green.log`: 13 transport tests pass. Final simplified startup code also passes the focused startup and auth-classification checks in run 06. Revocation signals terminal startup, cleans up, and raises a fixed credential-safe `TwitchError` while HOLD remains latched. |

Parent receipts and exact executed `.command.sh` files are in
`/tmp/agents/irl-shield/m3-r2/`. Snapshots `events-before.py` and
`transport-before.py` hash identically to the reviewed base production files.

Policy SHA-256: `aa359f9b70a580b768b755febea8433d77ff1402ee6c70771e1967348c92c082`.
Transport SHA-256: `b81768661ab5c8e5c55879e2e85f2f8c9686e4907a759572a7f827b5e0e596a3`.
Both production files and their affected tests are frozen; the receipt is
`/tmp/agents/irl-shield/m3-r2/frozen-source.sha256`. The model child received
the frozen policy. The transport change is independent
of the bounded policy model. Only validation HTTP 401 raises `InvalidToken`;
startup reports its terminal outcome directly as `TwitchError`.

## Resolved gate blocker

Run 05 attempted the combined gate: 149 tests, all 50 M3 tests passed, but an
unchanged root performance-queue test failed waiting for a subprocess marker
(`tests/test_perf_queue.py:422`). The expected macOS-only skip also occurred.
Run 06 retried that affected check alongside startup/auth checks: the root test
failed earlier at line 412, where its five-second unrelated sentinel had already
exited normally with code 0. Startup and auth checks passed. These are failures,
not a green gate. The conductor subsequently identified the test as an existing
root-owned timing flake, identical on main, with a five-second sentinel and a
three-second runner deadline. Root supplied a test-only correction with
injected-delay red/green proof. M3 has not changed the root test, queue, engine
or common code.

The conductor cherry-picked that correction as `9c86a70` from root's `e698aac`
and explicitly released the final-gate wait. Parent inspected the commit: only
`tests/test_perf_queue.py`, 11 added/8 removed lines. It replaces fixed sentinel
lifetimes with controlled blocking and waits for actual producer/stop states.
Root's supplied injected-delay proof is
`REPO_ROOT/.tmp/q/producer-stop-proof/proof.json`; M3 read it,
including both old failures/new passes and the root's 25-test affected pass.
Those root executions are not claimed as M3-run checks or added to M3's budget.
The four frozen M3 source/test hashes still verify unchanged after the pick.
Parent source was simplified after run 05 to avoid using `InvalidToken` as an
internal startup control signal, then verified by the focused run 06. Final
combined run 07 passed on those exact final bytes after the cherry-pick.

Parent R2 invocations used: **7**, including the completed final gate. Model child:
**3**, two unused. Prior cumulative count: **23**. Current exact total: **33/38**,
five unused. Root's queue test correction did not reset or expand this count.

All seven parent scopes are inactive/dead in `parent-process-exit.txt`.
All model scopes/JVMs exited, recorded in
`docs/model/evidence/r2/process-cleanup.txt`. No live Twitch, secrets,
personal keyring, extra scopes, installs, Mac or GPU work occurred.

No process, listener or queued survivor is retained. Conductor owns artifact
audit, commit and round 3 of PR #2; no merge/push authority was assumed.

## Model audit and bounded claim

The parent read the independent environment, both policy projections, config,
actual state-17 failure, fixed completion output, public replay source/output,
command runners, license records and process cleanup. The child's verified
manifest SHA-256 is
`6daf0fc1fba46c1b8b8ab313a9fe20e888b661a66ead0a8b87f455dc1bf1f52f`.
It was verified before and after copying only `docs/model/`; no checked TLA or
config byte was changed during integration. Frozen production hash matches.

`env.holds` stores raw Twitch stamp and local receipt independently. A release's
policy admission and discharge of the external obligation are separate updates,
so a broken policy can go LIVE while the obligation remains true. The two
policy projections differ only in the actual protective-order clamp and their
identifying module/comment. All six invariant formulas are unchanged. The raw
counterexample is `docs/model/evidence/r2/old-clamp.tlc.log`; fixed pass is
`fixed-pass.tlc.log`; concrete replay is `public-replay.log` in the same folder.

The fixed graph retains observed fault, queued welcome, subscription enabling,
generation/query fences, completion callback microsteps, Shield repair, planned
handover and independent local/coverage holds. Bounds: three generations, two
query identities, one hold per source, holds delivered at local time 10 and
serialized releases at 11. Separate raw stamps include +10/+29 skew, equal/older
releases, missing/pre-start and beyond-bound cases. A pathological future stamp
uses the owner's explicit 30-second cap; it does not promise raw-order protection
forever. A legitimate newer release is still required; holds do not auto-expire.

The graph does not prove arbitrary clock movement, repeated unbounded holds,
release callback reentry, payload authorization, replay-cache eviction, progress,
silent-loss detection, complete WebSocket/watchdog behavior, live Twitch or
media privacy. Its fingerprint collision estimates are recorded in REPORT.md;
the result is bounded model evidence, not an implementation correctness
probability. R1's policy-derived release obligation was model drift masking a
real product bug; the new old-spec failure and actual source replay expose it.

## Exact invocation ledger

Every parent row has the same numbered `.command.sh` and `.log` basename under
`/tmp/agents/irl-shield/m3-r2/`. Each runner contains the actual executed command,
not a reconstructed recipe. It is invoked from the assigned worktree.

| Parent run | Result |
| --- | --- |
| `01-policy-red` | Two tests, six assertion/subtest failures against unchanged reviewed policy. |
| `02-policy-green` | All 17 policy tests pass. |
| `03-startup-red` | One test, three startup route failures against unchanged reviewed transport. |
| `04-transport-green` | All 13 transport tests pass, 53.556 s. |
| `05-combined-gate` | 149 tests, one root queue failure and one macOS skip; all 50 M3 passed. Not a passing gate. |
| `06-focused` | Root queue test fails earlier on ended sentinel; startup and auth classification pass on final source. Not a passing suite. |
| `07-combined-gate-final` | Exit 0 on `9c86a70` plus frozen uncommitted M3 changes: 149 tests, 148 passed, one expected macOS-only skip; all 50 M3 passed. |

The three model invocations are direct old TLC (exit 12), fixed TLC (exit 0),
combined public replay (exit 0). No config failure or extra model retry occurred.
Exact commands and tool hashes are in `docs/model/evidence/r2/commands.sh`,
`run-tlc.sh`, `run-public-replay.sh` and `model-and-tool.sha256`. Existing tools
were read-only. The fixed graph used 1 GB heap, two workers and the 2 GB scope;
its live limit receipt is preserved.

## Interfaces, test boundaries and unchanged dependencies

The public `ShieldEvents.accept()` result and underlying Control output own the
timestamp regression. Existing out-of-order tests used past timestamps, which
missed the forward clamp. The new skew table checks older, equal and newer
Twitch order for both chat and Shield Mode. The revised existing extreme-future
test checks the prescribed 30-second bound. No export or test-only policy hook
was added. Unusable/pre-start/expired protective stamps still fall back to local
receipt, protective admission still never depends on the clock, and release
authorization/generation/session/dedup/floor guards are unchanged.

`EventSubClient.start()` owns startup settlement. The real loopback server
supplies validation 401 at two startup stages and a real WebSocket revocation
at the third. The test observes the returned error, held output and closed
server sockets. Existing idle-revocation coverage began after successful start
and could not catch this hang. Only the synthetic HTTP/server boundary was
extended; all its transport callers ran in the affected suite.

Startup terminal signalling stays on the owner loop. It does not turn transient
network/5xx failures into revocation, change policy phases or release a hold.
The public transport, key-provider and engine.hold integration interfaces are
unchanged. The exact approved OAuth scopes remain unchanged.

No dependency, model weights or dataset was added or installed. Existing license
records remain in `LICENSES.md`, `DEPENDENCIES.json` and the model report:
pyTwitchAPI 4.5.0 MIT, optional keyring 25.6.0 MIT, Twitch CLI 1.1.24 Apache-2.0,
TLC distribution 1.7.4 MIT and Temurin 25 GPL v2 with Classpath Exception.
Every suite and model invocation remains in the prescribed systemd slice with
2 GB memory cap, 200% CPU, niceness 10 and native worker limit two; TLC heap is
at most 1 GB. No production Twitch endpoint, credentials, personal storage,
media, detector, scorer, OCR quality evidence or performance measurement was
exercised by this round.

## Final artifacts and limits

Parent scratch is `/tmp/agents/irl-shield/m3-r2/`: exact command runners and
logs 01 through 07, before-fix production/test snapshots, frozen-source hashes,
child/integrated model manifest verification, `final.diff` (including untracked
files), `git-status.txt`, `tracking-check.txt`, `parent-process-exit.txt` and
`raw-receipts.sha256`. Final owned source/doc/test hashes are in
`shield/twitch/SHA256SUMS`; the unchanged accepted model manifest remains
`docs/model/SHA256SUMS`. New R2 deliverables remain untracked intentionally.
The index is empty and `git diff --check` passes. No worktree, branch, index,
commit, push, PR state or global configuration was changed by M3.

Remaining verification: conductor audit/commit/round 3, live authorization and
platform acceptance. The Linux run skips the macOS-only VideoToolbox test;
no Mac compatibility result is claimed from that skip. No detector/media path
changed and no new OCR scorecard or performance measurement is claimed.

Verdict: **three R2 findings addressed; 148 passed / 1 expected skip; six
invariants / 14,747,184 fixed model states; 33/38 invocations; zero survivors;
uncommitted fixes ready for conductor round 3.**
