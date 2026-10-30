# M3 Twitch offline implementation hand-back

**PASS for the offline milestone:** 128 executed tests passed, 1 macOS-only test
skipped, including **30/30 M3**; current TLC baseline/restored each checked **8
invariants, 50,920 distinct states**, with no violation. All **48/48** permitted
test/TLC invocations were used. Live Twitch login, ingestion and platform acceptance
remain unverified and unauthorized tonight.

## Checkout and owned changes

Actual/requested branch: `elannash/m3-twitch` / `elannash/m3-twitch`.
HEAD/base remains `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`.
Dedicated checkout: `/home/elan/.t3/worktrees/irl-shield/t3-3bb00dac`.
First operation verified isolated path, exact HEAD and clean status; the prepared
`t3/m3-twitch` branch was renamed in place. No worktree creation/removal, staging,
commit, push, PR or merge was performed. Final `git status --short` contains only:

```text
?? docs/model/
?? shield/twitch/
?? tests/m3/
```

These are intentionally new, unstaged files. `git ls-files --error-unmatch` fails
for the new module/test/model paths; no tracked-delivery claim is made. The full
file list is `/tmp/agents/irl-shield/m3-twitch/deliverables.json` and source hashes
are in `/tmp/agents/irl-shield/m3-twitch/final-code.sha256` and `SHA256SUMS` beside
this hand-back. `git diff` is empty because the files are untracked, not because
there is no implementation. No common engine, Control, bench/scorer/cache,
requirements, transport or root README file was edited.

- `shield/twitch/auth.py`, `http.py`, `storage.py`, `keys.py`: owned device grant,
  safe credential values, cancellation/expiry/interval/slow_down, exact scopes,
  serialized RAM refresh/validation, explicit OS keyring seam, fixed-origin HTTP,
  and tiny async `KeyProvider.get_key() -> Secret` for in-process M2 use.
- `shield/twitch/events.py`, `transport.py`: actor/role policy and source-keyed
  holds on the existing `engine.hold` seam; real pyTwitchAPI WebSocket adapter;
  bounded deduplication/session-time filtering; reconciliation, planned handover,
  outage/revocation HOLD and idle validation/shutdown.
- `tests/m3/`: public-interface auth/HTTP/Helix, policy/replay, real local WebSocket,
  actual pinned Twitch CLI, and final portable functional-gate runner.
- `docs/model/`: current finite TLA+ model, config, complete raw receipts, exact
  commands, licenses, bounds, Mermaid trace and historical pre-reconciliation evidence.

All project source was authored in this Codex family inside the hackathon window.
Auth and model children used explicitly authorized GPT-6.1 Sol Ultra/priority,
isolated worktrees and disjoint files. Parent audited source, hash manifests,
raw logs and scope cleanup before copying. No non-Codex project code was imported.

## Resulting behavior

The requested scopes are exactly `user:read:chat`, `moderator:read:shield_mode`,
`channel:read:stream_key`. The broadcaster owns the user token; subscription
identities and key retrieval are tied to that validated ID. No bot/app-token
permissions or write/manage scopes were added.

Tokens and keys are RAM values by default. They redact string/repr output and
reject pickle/JSON serialization. The only credential persistence seam requires
literal `remember=True` and an accepted OS secure backend; tests use mock keyrings.
HTTP errors contain fixed local reasons rather than remote bodies. No real client
ID, code, token or stream key was read, fetched, written or logged. An attended
owner presenter writes activation information to `/dev/tty`, without stdout,
browser subprocess arguments or a secret-bearing file; no presenter was opened here.

Only a matching broadcaster ID or trusted moderator badge can chat-hold; only the
broadcaster ID can chat-resume. Display names grant no authority. Resume releases
`chat` only. `shield_mode`, `local`, and `twitch-connection` remain independent.
Shared-chat origins are ignored; stale resumes and Shield end ordering fail closed.
The bounded ID cache advances a permanent timestamp floor on expiry/eviction, so
old IDs do not become executable after reconnect. Unseen late messages at/below
that floor are deliberately rejected too.

Startup and unplanned recovery hold through subscriptions and Helix Get Shield Mode
Status. Active status asserts `shield_mode`; inactive status cannot erase a newer
accepted Shield event. A stale generation cannot release a later outage. Failed
status calls remain held and retry with 1,2,4,8,16,30-second capped backoff. A planned
Twitch handover adds no hold; failure/30-second timeout enters unplanned held recovery.
The owned adapter uses pyTwitchAPI's I/O, migration and resubscription, with pinned
private hooks for raw envelope policy, host/redirect guards and cleanup.

No chat-history API is used or invented for commands sent during an outage. Video
is already held during that window; after recovery, Shield status is reconciled and
preexisting chat/local holds remain. `Control` still owns HOLD > PROTECT > LIVE;
the adapter does not compute or override coverage.

## Receipts and semantics

Final command was the single combined Python gate in `LOG.md`, executed by parent
at nice 10 in `app-t3code-agents.slice` with CPUQuota 200% and BLAS/OMP limits 2:

```text
tests: 96 methods; tests/m2: 3; tests/m3: 30
Ran 129 tests in 31.186s
OK (skipped=1)
```

Raw log: `/tmp/agents/irl-shield/m3-twitch/22-full-functional-gate.log`, exit 0.
The skipped case is `test_pipeline.DelayedVideo.test_lookahead_preserves_every_frame_in_order_including_tail`:
`VideoToolbox requires macOS`. No ResourceWarning/error traceback occurred in the
final log. The gate also parsed all Python source in the repo's functional targets.
It does **not** replace root's Mac Swift/VideoToolbox gate; `swiftc` is unavailable
on this host and `scripts/check` requires that platform step.

The final M3 tests include the actual checksum-pinned Twitch CLI server: Shield Mode
begin/end, planned reconnect and exit. CLI v1.1.24 lacks chat subscriptions/generation;
a local facade supplies only that synthetic subscription response and forwards the
real socket bytes/Shield subscriptions to CLI. Chat authority/replay/revocation run
over the separate actual pyTwitchAPI localhost transport. All Python sockets are
guarded against nonlocal endpoints. CLI's upstream internal RPC binds fixed port
44747; tests refuse to start if it is already owned and terminate their own server.
Its synthetic receipt is `/tmp/agents/irl-shield/m3-twitch/cli-server.log`.

Current model receipts are in `docs/model/REPORT.md` and
`docs/model/evidence/reconciliation/`. Baseline and restored each exhausted the
finite graph: 1,139,021 generated, 50,920 distinct, 0 queued, depth 18. The direct
clobber mutation failed `ReconcileReleaseIsolated`, exit 12, after two transitions:
Init → begin_reconcile → reconciled(active=True). The incorrect mutant reached
PROTECT by erasing Shield HOLD. Final Python test
`test_tlc_release_clobber_shortest_path_retains_active_shield` replays exactly those
public calls and keeps HOLD.

Parent production mutation proof:
`21-reconcile-mutant.log` shows both the exact-path test failing (PROTECT instead of
HOLD) and the source-isolation test failing (local release reached LIVE). The receipt
`21-mutation-receipt.json` confirms applied mutant SHA
`084c07382354126e80c9c3841d55e4fbbadf42a9a8deea1e4c10e61215b9ebf0` and byte-for-byte
restore to `c632045a328442afd25ac4103878d1bd067cf0f3d19bb8641eb9e0ee0280c40f` before the
green final gate. Earlier authority and cache-reset production mutations also failed
their intended assertions, as recorded in `16-role-mutant.log` and `17-replay-mutant.log`.

TLC bounds are capacity 1, six immutable representative envelopes, five clock values,
two fault generations, one retained snapshot and atomic public calls. This is not
a proof of arbitrary capacities, thread scheduling, eventual recovery, total memory,
the unbounded Control transition ledger or the media pipeline. No OCR/quality scorecard
is claimed; this lane did not run Q or modify detection/masking/scheduling/media egress.

## Licenses, installations and hashes

See `LICENSES.md` and `DEPENDENCIES.json` for every introduced/resolved library and
tool license/source. Direct pins: pyTwitchAPI 4.5.0 MIT; keyring 25.6.0 MIT. In
particular, enum-tools 0.13.0 is LGPL-3.0-or-later, recorded rather than assumed MIT.
Twitch CLI 1.1.24 is Apache-2.0, extracted with LICENSE/NOTICE/THIRD-PARTY intact.
Archive hash `9cae4e9cd52e66fb4dda6b633b3276a4450a28a83dea7a4651a42a67372eed8f` matched
the official published checksum; executed binary hash
`40958ae7aed8a58f58bd9f32dec98cdd326741e5f9c1c6e6da9f7ae1df599240` is asserted by the test.
TLC 1.7.4 MIT and existing Temurin 25 GPLv2+Classpath Exception were reused read-only.
No new model, dataset or media asset was introduced.

Task-local installs are `.tmp/m3/venv`, `.tmp/m3/py311`, `.tmp/m3/wheels`,
`.tmp/m3/uv-cache`, and `.tmp/tools/`. No global configuration/system/CUDA changes,
sudo, payment or new account. `install-py311.log` and `wheels.sha256` are in the raw
receipt folder. Initial Python 3.14 exploratory runs remain in the ledger; the final
functional result uses existing Python 3.11.14. No `.env` or environment dump was read.

Key final hashes (SHA-256):

- events: `c632045a328442afd25ac4103878d1bd067cf0f3d19bb8641eb9e0ee0280c40f`
- transport: `514356e5c0434f5066d1df42a4eb70f85944533d525331f8329cbea4269bccea`
- current TLA+ model: `4ceb8066e37dd3e9bb3162f123d9e3c29bf0d5688e6c5aa23727a330cb5c5c50`
- current model report: `49577a08dcf846e04fb617e203d59e55a2fec52a8686e8ec78cf505965119040`

## Remaining root work and cleanup

Root must add the owned requirements to installation, wire the CLI/launcher to the
documented interfaces on the same engine, and pass `KeyProvider` to M2's in-process
egress seam. `PROTOCOL.md` supplies the exact launch composition with `TWITCH_CLIENT_ID`
injected through `infisical run --`. Root must preserve bandwidth-test-only ingest
until the owner authorizes a live session. This lane added no CLI, stream destination,
ingest URL or publishing behavior outside its scope.

The public device-flow registration, real Twitch responses/TLS, real keyring backends,
owner terminal presentation, Mac/Windows and actual Twitch egress still need attended
acceptance. Twitch's general refresh page conflicts with its device-flow-specific
public-client refresh guidance; that inconsistency and the selected specific contract
are cited in `PROTOCOL.md`, with no scope broadening. If explicit remember is wired,
root must save the latest rotated pair; a crash before persistence may require login.

All owned processes and children exited. The final scope was
`irl-shield-m3-final-gate.scope`; post-run `systemctl` returned not-found/inactive/dead.
No retained PID, port or stop command is handed off. Final process inventory:
`/tmp/agents/irl-shield/m3-twitch/final-processes.json`. All CLI runners, aiohttp servers,
socket threads and idle timers were closed/awaited by test cleanup. Child scope
cleanup receipts are retained in their model/auth reports. Existing harness/root/Mac
processes were left untouched. Scratch remains for conductor audit; no scratch is
treated as a demo asset.

The conductor owns independent review, integration, its own full platform gate and
milestone commit/PR. No implementation tests were omitted to make the count green;
the single platform skip and all failed/red attempts are named in `LOG.md`.
