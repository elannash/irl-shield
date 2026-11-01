# M2 Gate 2 implementation hand-back

Verdict: IMPLEMENTED, NATIVE EXECUTION PENDING. The artifact unit checks pass;
no functional/native soak or privacy pass is claimed. Q is not qualified.

## Isolation and scope

- Actual/requested checkout: `WORKTREE_t3-414a256a`.
- Initial branch: `t3/414a256a`; renamed in place to requested
  `elannash/m2-gate2-harness`.
- Initial/final HEAD: `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`.
- Initial status was clean. All six assigned files are new and untracked:
  `relay/soak.py`, `relay/fixture.py`, `relay/seal.py`, `scripts/m2-soak`,
  `tests/m2/test_seal.py`, and this hand-back. Scratch is under `.tmp/gate2/`.
- No stage, commit, push, PR, merge, worktree creation/removal, dependency
  install, parent-tree write, new subagent, GPU inference, native encoding,
  MediaMTX launch, listener, Twitch action, or Mac operation was performed.
- Model/runtime assignment: authorized GPT-6.1 Sol Ultra lane. This runtime
  provides no separate priority-tier receipt; priority was requested in the packet.
- Code was authored in this authorized Codex child on 2026-10-30 UTC.
  The packet's original approximately 03:55–11:55 UTC timebox was retained.

The first shell operation was exactly:

```sh
pwd; git branch --show-current; git rev-parse HEAD; git status --short
```

It returned the checkout above, `t3/414a256a`, the pinned HEAD, and no status
entries. The only branch mutation was:

```sh
git branch -m elannash/m2-gate2-harness
```

## What the parent receives

`relay/soak.py` calls the parent's `make_engine(cache, provider='cuda', faults=...)`
and `runtime.run(...)`; it contains no copied/forked masking engine. It uses
`MediaMTX`, `Credentials`, `RelayAddress`, and the `control_ready` callback from
the parent drafts. Parent-owned source files were read, never edited.

The CLI defaults to 1200 observation seconds. It adds eight seconds of runtime
headroom for the independent reader to join; the measured capture must still
contain at least the requested span and requested 30fps frame count. The
default fixture is the existing `sf-market` tune clip. `--functional` accepts
20–120 seconds. Optional `--srt-capture` adds a second independent reader.

The publisher loops verified licensed prepared footage, discards all original
audio, and adds two original synthetic labels, per-frame optical stamps,
flashes, and frequency-coded timing beeps. Source metadata retains the public
source URL, author, license, prepared/original hashes from the frozen manifest,
absolute fixture path, and benchmark-only scope. Per-frame sender rows retain
label boxes/times, actual decoded source PTS/time base, synthetic index, epoch
stamp, and pixel/PCM hashes. These derivatives are BENCHMARK-ONLY, not demo-ready.

The fault plan injects a five-second accurate-lane stall through the shared
factory's `faults` argument. At `4 + seconds * .55`, a separate local HOLD
source activates; one second later the owned sender is SIGKILLed, four seconds
after HOLD it reconnects, and seven seconds after HOLD the local HOLD releases.
Actual callback times are saved separately from the plan. Reconnect cannot
clear that source through the harness itself. This behavior is unverified natively.

The network readers remux actual MediaMTX packets to `rtmp/network.mkv` and
optionally `srt/network.mkv`; they never receive engine pixels. Packet hashes
and arrival times accompany each capture. The runtime's `encoded.flv` and
`frames.jsonl` remain its archive and full mask receipts. After native runtime
cleanup, each independent capture is decoded to `decoded.jsonl`, with PTS/time
bases, decoded hashes, optical matches, audio onsets, and spatial-content flags.
`protection.jsonl` projects the runtime mask/protection timeline for review.

A/V offsets pair a decoded flash onset with a tone whose frequency identifies
the source pulse modulo 16. Pairing is unambiguous only within +/-8 seconds;
missing/partially hidden flash onsets are excluded rather than assigned zero.
Receipts include the pairs, unmatched counts, median offset, and absolute p95.
No numeric A/V result exists yet. The spatial-content heuristic is a functional
guard, not an OCR or privacy score.

Summary status becomes incomplete for absent/short/discontinuous RTMP A/V,
missing measurable timing, unobserved reconnect/HOLD/stall protection, absent
LIVE spatial video, unfinished faults, sender errors, or queue overflow.
`gate2_privacy_pass` is always false. Corrected independent OCR grading remains
pending after PR1 merge, including for an eventual successful functional run.

## Guards, cleanup and sealing

- Fixed assigned ports: RTMP 19550 / SRT 19050. Listener host is restricted
  to `127.0.0.1` (default) or `100.109.49.77`; observed MediaMTX sockets are
  checked against that address/port set.
- Timed mode requires `IRL_SHIELD_PERF_QUEUE_LEASE_FD` to identify the canonical
  `/tmp/agents/irl-shield/perf.lock` device/inode and have a kernel-reported
  exclusive FLOCK in `/proc/self/fdinfo`. No nested flock is acquired.
- Functional mode discovers the same inherited canonical exclusive descriptor
  from `scripts/host-lock`. Both modes require `app-t3code-agents.slice`, lower
  their own priority to nice 10 if needed, and cap native library workers at 2.
- Credentials are generated per run and used only by in-memory PyAV opens,
  parent MediaMTX stdin, and multiprocessing's private spawn pipe. No generated
  credential or authenticated URL is placed in command argv or saved receipts.
  Libav logs are quiet; credential-bearing exception strings are suppressed.
- Raw encoded capture writes have no Python packet queue; the parent runtime
  input queue is bounded at 8. Engine buffer/poll bounds and lane sample bounds
  are declared in provenance; RSS KiB, threads, and FDs are sampled for owned
  harness/MediaMTX/sender PIDs only. There is no measured resource result yet.
- Sender, capture, engine, and MediaMTX cleanup is attempted on failure as well
  as success. Process exit receipts are saved on a native run. A cleanup error
  leaves the directory explicitly unsealed rather than hashing active writers.
- `seal()` sets files read-only and hashes the complete file inventory.
  `verify(directory, expected_sha256)` checks the externally retained seal
  digest, symlinks, file inventory, byte lengths, and every content hash.
  This is content-addressed, tamper-evident evidence; chmod is not the proof of
  immutability. The parent must retain the printed digest outside the directory
  and verify it immediately before grading. Do not trust a digest regenerated
  from the directory being graded.

No native child processes were started in this implementation lane. All shell
and Python check processes completed; there is no listener/process handoff.

## Test allocation: 6 / 6 used

Chosen public seams: `seal`/`verify` own evidence integrity; `describe_source`
owns license/split/hash admission before any networking. These tests do not
exercise PyAV, CUDA, MediaMTX, fault timing, or native cleanup. The synthetic
test data contains no credentials and no private/user media.

Logs live at
`WORKTREE_t3-414a256a/.tmp/gate2/logs/`.

1. Expected red: changed capture was wrongly accepted under the unchanged seal.
   One test, one failure (`ValueError not raised`). The shell wrapper returned
   0 because its last command was `cat`; the log records the unittest failure.

   ```sh
   nice -n 10 python3 -m unittest discover -s tests/m2 -p test_seal.py > .tmp/gate2/logs/01-seal-red.log 2>&1; cat .tmp/gate2/logs/01-seal-red.log
   ```

2. Green after content/inventory verification: one test passed, exit 0.

   ```sh
   nice -n 10 python3 -m unittest discover -s tests/m2 -p test_seal.py > .tmp/gate2/logs/02-seal-green.log 2>&1; result=$?; cat .tmp/gate2/logs/02-seal-green.log; exit "$result"
   ```

3. Expected red: changed fixture bytes were admitted. Two tests, one failure
   (`ValueError not raised`), exit 1.

   ```sh
   nice -n 10 python3 -m unittest discover -s tests/m2 -p test_seal.py > .tmp/gate2/logs/03-source-red.log 2>&1; result=$?; cat .tmp/gate2/logs/03-source-red.log; exit "$result"
   ```

4. Green after source SHA admission: two tests passed, exit 0.

   ```sh
   nice -n 10 python3 -m unittest discover -s tests/m2 -p test_seal.py > .tmp/gate2/logs/04-source-green.log 2>&1; result=$?; cat .tmp/gate2/logs/04-source-green.log; exit "$result"
   ```

5. Final artifact suite: five tests passed, exit 0. It covers changed bytes,
   added/deleted/symlinked files, replaced seal metadata, changed source bytes,
   and held-out/unlicensed admission.

   ```sh
   nice -n 10 python3 -m unittest discover -s tests/m2 -p test_seal.py > .tmp/gate2/logs/05-final-unit.log 2>&1; result=$?; cat .tmp/gate2/logs/05-final-unit.log; exit "$result"
   ```

6. CLI help/import: exit 0, using the parent's private Python read-only.
   It imports harness source but does not import/load native engines or media.

   ```sh
   nice -n 10 WORKTREE_t3-ae860af9/.tmp/m2/py311/bin/python scripts/m2-soak --help > .tmp/gate2/logs/06-help.log 2>&1; result=$?; cat .tmp/gate2/logs/06-help.log; exit "$result"
   ```

After invocation 6, static review added the script's multiprocessing-safe
`__main__` guard, actual decoded source PTS fields, and exact interpreter argv
plus resolved config in provenance. No further check was run: the allocation
was exhausted. The seal/source admission implementation and tests were
unchanged after their passing final run. Parent integrated/native validation
and the parent's final full gate remain required.

## Code, model and tool receipts

No installs or downloads were performed. Existing dependencies are declared in
`requirements-relay.txt` and `requirements-linux-gpu.txt`. New generator code
uses Python stdlib, existing PyAV (BSD-3-Clause; bundled FFmpeg LGPL), NumPy
(BSD-3-Clause), and OpenCV (Apache-2.0). Original synthetic overlay/tone output
is declared CC0-1.0 in `relay/fixture.py`; the base footage retains its license.

SHA-256 read directly from final files:

```text
79ce4c10aeb00ba0cbc67939c780369e20cc9d37d7f6348394541fa573b4ea96  relay/soak.py
c386d2bd0b4c737173e67ba6dd6fb58c1349a3ff80ebf5807a55b910f84692ee  relay/fixture.py
effe7bb8e29b3f4db539fbfb7204234151f1772c4bcddd9c0b120366d002c24e  relay/seal.py
3491c51fc9204fa80eb8f5db8032fdc4fc5d09f5ba8fd3a57886343f7f85fb9d  scripts/m2-soak
a663bec891ea442c3ff32b8498fffbd1c90c22570a7e56490f6e8bcb00734796  tests/m2/test_seal.py
52b8d5ee27aaf872801d91ba0f181b6ea1f068689b4d805b39fa2487ba651316  models/manifest.json
40d874198abb127eb3031da0fb4fc5ecc9b401ad82fb9509d55b51d583a3799c  fixtures/manifest.json
```

Read-only parent MediaMTX binary SHA-256 was measured as
`bfa372a169751bbf6da2ebddcbcd2f7d3ab3dca3cc553022162eda36fe03e73d`.
It is v1.21.3, MIT; its release archive SHA supplied in the packet is
`0a2ea7eba96023631efa1bea7804823a9145b043b6646a8a05798d4ac24ed635`
(archive bytes were not rehashed here). No binary was executed.

Model hashes/licenses below are manifest declarations, not new verification
of loaded weights (no model was loaded in this lane):

- Tiny: `193bab7a04fca699a6c82e6abb5b81bdb28177f0abd4062552b04908dafb19f8`,
  Apache-2.0, `models/manifest.json:158`.
- Small: `d73e0058b7a8086bbd57f3d10b8bcd4ff95363f67e06e2762b5e814fe9c9410e`,
  Apache-2.0, `models/manifest.json:90`.
- `sf-market` prepared clip:
  `bed20032b30bcdfebb32f137809b71cedf8486c7881020e5e955a91aa28aca7c`,
  CC BY 3.0; `fixtures/manifest.json` and `fixtures/ATTRIBUTION.md`.
  The CLI will verify actual fixture bytes before starting native work.

Primary technical sources consulted: the pinned
[PyAV 16.0.1 remux example](https://github.com/PyAV-Org/PyAV/blob/v16.0.1/examples/basics/remux.py)
and [output implementation](https://github.com/PyAV-Org/PyAV/blob/v16.0.1/av/container/output.py)
support template-based packet remuxing. [PyAV time documentation](https://pyav.org/docs/stable/api/time.html)
describes frame/stream time-base handling.
[MediaMTX SRT documentation](https://mediamtx.org/docs/features/srt-specific-features)
documents stream-ID action/path/credential fields. Parent interfaces were read
at `relay/runtime.py`, `live.py`, `stream.py`, `security.py`, and `mediamtx.py`
in the parent tree; engine/control/fault internals were read locally.

## Parent integration and enqueue templates — not executed

Copy the six assigned paths to the parent, preserving the executable bit on
`scripts/m2-soak`. Keep its live/runtime/stream/security/MediaMTX implementations.
The isolated child does not contain those untracked parent modules, so only
help/artifact unit tests are runnable here as-is. No parent engine snapshot
was made. The runtime factory inspected uses exactly
`Tiny8Hz640Small4Hz960D1phase320floor.05pad.3B6/A30`.

Use the root's new queue, model cache, and run window. This enqueue command
registers a job only; it does not start/reopen a queue. It assumes the parent
queue runner itself runs in `app-t3code-agents.slice`. Do not wrap the timed
job in another flock or a launcher that drops the inherited lease descriptor.

```sh
PARENT=WORKTREE_t3-ae860af9
"$PARENT/scripts/perf-queue" --queue-dir "${QUEUE_DIR:?root must supply the new queue}" \
  enqueue linux m2-gate2-native --lane root --cwd "$PARENT" \
  --receipt "$PARENT/.tmp/m2/gate2/attempt-{attempt}/summary.json" \
  -- "$PARENT/.tmp/m2/py311/bin/python" -m relay.soak \
  --seconds 1200 --output "$PARENT/.tmp/m2/gate2/attempt-{attempt}" \
  --model-cache "${MODEL_CACHE:?root must supply the existing model cache}" \
  --fixture-root "$PARENT"
```

A short functional command for the parent's exclusive window is:

```sh
PARENT=WORKTREE_t3-ae860af9
cd "$PARENT"
systemd-run --user --scope --slice=app-t3code-agents.slice \
  nice -n 10 scripts/host-lock exclusive .tmp/m2/py311/bin/python -m relay.soak \
  --functional --seconds 30 --output .tmp/m2/gate2/functional-unique \
  --model-cache "${MODEL_CACHE:?root must supply the existing model cache}" \
  --fixture-root "$PARENT"
```

Optionally append `--srt-capture` to a short run first; SRT support in this
PyAV build and the entire SRT path remain unverified. Each run needs a fresh
output directory. Do not reuse an incomplete or sealed attempt directory.

Before root grading, use the digest retained in the original queue stdout:

```sh
.tmp/m2/py311/bin/python -m relay.seal "$EVIDENCE_DIR" \
  --expected-sha256 "$RETAINED_SEAL_SHA256"
```

Open `summary.json`, `runtime.json`, sender exits, listener receipts, capture
transport/decoded receipts, and the retained video before accepting native
evidence. The parent owns any requested native retry/full gate and corrected
independent OCR grading. No existing fixture derivative is demo-ready.
