# M2 ingest-security hand-back

Verdict: PARTIAL — startup ownership bug fixed with red/green proof; real SRT ACL and packet transfer pass on loopback and assigned Tailscale IP; strengthened RTMP media-read proof remains red. Six of six permitted test invocations spent. No full repo gate, staging, commit, push, PR, or merge.

## Checkout and scope

- Requested and actual cwd: `WORKTREE_t3-ea758545`.
- Initial branch `t3/ea758545`, renamed in place to requested `elannash/m2-ingest-security`.
- Initial/final HEAD: `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d` (exact requested HEAD).
- First operation: `pwd; git branch --show-current; git rev-parse HEAD; git status --short`. Output confirmed this isolated prepared worktree and a clean initial status. No shell worktrees created/removed.
- All seven deliverable paths are untracked/uncommitted relative to that HEAD: `relay/security.py`, `relay/mediamtx.py`, `relay/native_auth.py`, `scripts/m2-tools`, `scripts/m2-native`, `tests/m2/test_security.py`, and this file. `git ls-files --error-unmatch` explicitly failed for the six source/test/script paths, as expected under the no-stage instruction. Parent must add them when authorized.
- Six initial source/test/script files copied from the authorized parent `WORKTREE_t3-ae860af9`; no preexisting parent hand-back existed. Parent tree remained read-only. No edits to `relay/live.py`, `relay/runtime.py`, engine, scorer, cache, requirements, or root README.
- No children spawned. Runtime identifies this lane as GPT-6.1 Sol with Ultra reasoning; the packet authorized that assignment. No additional model execution or detector/model changes.

## Changes and interface

- `relay/mediamtx.py:31`: retains `MediaMTX(address, phone, internal, binary=None)` and the same context interface. Startup now requires the child's own TCP RTMP and UDP SRT listening sockets at exactly the requested addresses/ports; an incumbent port cannot satisfy readiness. Both TCP and UDP occupied-port cases are in the real native probe.
- `relay/mediamtx.py:87`: socket proof intersects `/proc/<pid>/fd` socket inodes with `/proc/<pid>/net/{tcp,tcp6,udp,udp6}`. TCP connected sockets are excluded from listener rows. IPv6 listeners are rejected. A disappeared child yields no listeners.
- `relay/mediamtx.py:34`: ambient `MTX_*` overrides are stripped. The complex users and exact two paths still travel as JSON over stdin; only scalar settings reach the child environment. Explicitly disables recording and packet dumping. No wildcard/default path, publisher replacement, or extra protocol listener. Stdout/stderr remain `/dev/null`.
- `relay/mediamtx.py:62`: ordinary startup failures become a static exception without chained upstream text; started children are reaped, including when a config pipe closes early. The context cannot be reused with the same runtime credentials.
- `relay/security.py:38`: credentials hide both username and password in repr. Existing RelayAddress(host, rtmp_port, srt_port), `.rtmp(path, creds)`, `.srt(action, path, creds)` and TwitchStub interfaces are unchanged. TwitchStub remains memory-only with `bandwidthtest=true` and no network implementation.
- `relay/native_auth.py:21`: probe-only ctypes adapter uses the already installed system libsrt 1.5 public C ABI. No new Python/native dependency was installed. Credentialed URLs exist only in memory; libav and libsrt diagnostics are disabled before credentialed calls. The native probe now verifies real reads rather than declaring success after one muxed packet; failed probes remain red.
- `relay/native_auth.py:203`: successful SRT publish handshake precedes track parsing; positive SRT readers retry the real connection for a bounded four-second window. This fixed the SRT reader race evidenced by invocation 05. RTMP readers still make one attempt; see unresolved item below.
- `relay/native_auth.py:242`: actual auth matrix checks anonymous/bad publication, phone egress publication denial, internal camera publication denial, unknown paths, camera read restrictions, valid camera publication/internal read, internal shielded publication/anonymous read. Positive readers must receive at least three packets. SRT packets also have MPEG-TS sync/size checks. These are transport/auth checks, not a decode, visual-quality or throughput benchmark.
- The native receipt confirms both runtime credentials absent from `/proc/<pid>/environ` and `/proc/<pid>/cmdline` without retaining either file or any values, and checks fd 1/2 point at `/dev/null`. Failure receipts include exception type and frame locations only, never raw upstream messages or locals.
- `scripts/m2-native:5` accepts optional `M2_PYTHON` to reuse an existing environment without creating/copying one; added CLI `--rtmp-port`, `--srt-port`, `--tool-directory` keep probes isolated and binary verification intact. Defaults for native probe ports are 19450/18950; runtime RelayAddress defaults are unchanged.
- `scripts/m2-tools:25` also verifies the pinned binary hash before recording it. Installer download itself was not run in this lane.
- `tests/m2/test_security.py:15`: existing assertions use boolean comparisons for secret-bearing values, so failure output does not include credentials or synthetic stream keys. Added username repr coverage. No production-only test flags or exports added.

## Test receipts — exactly six process invocations

All commands ran from this checkout. Logs, repro scripts, native JSON, parent-relative patches and final source hashes are in ignored scratch `WORKTREE_t3-ea758545/.tmp/ingest-security/`.

1. **RED**, exit 1. `PYTHONPATH="$PWD" WORKTREE_t3-ae860af9/.tmp/m2/py311/bin/python .tmp/ingest-security/occupied_port.py > .tmp/ingest-security/01-occupied-red.log 2>&1`
   - Exact symptom: `AssertionError: MediaMTX accepted an incumbent listener as its own readiness`.
   - The repro binds/listens on loopback 19450 and calls the actual MediaMTX context using the verified parent binary, then asserts its own child exited. It does not substitute a fake server.
2. **GREEN**, exit 0, identical repro after startup fix. `PYTHONPATH="$PWD" WORKTREE_t3-ae860af9/.tmp/m2/py311/bin/python .tmp/ingest-security/occupied_port.py > .tmp/ingest-security/02-occupied-green.log 2>&1`
   - Output: `Occupied RTMP listener rejected; owned child exited`.
3. **FAILED**, exit 1. `M2_PYTHON=WORKTREE_t3-ae860af9/.tmp/m2/py311/bin/python scripts/m2-native --fixture REPO_ROOT/out/offline-vision-union-a30/sf-market-natural-input.mp4 --host 127.0.0.1 --rtmp-port 19450 --srt-port 18950 --tool-directory WORKTREE_t3-ae860af9/.tmp/tools/mediamtx-v1.21.3 --output .tmp/ingest-security/03-native-loopback.json > .tmp/ingest-security/03-native-loopback.log 2>&1`
   - Only generic sanitized failure retained; there is no 03 JSON receipt. The particular failure cannot be established from that log.
4. **FAILED**, exit 1. Same command as 03 with output/log prefix `04-native-loopback`.
   - `04-native-loopback.json`: sanitized OSError frame points at occupied-port bind. The probe's TCP incumbent was then changed to use SO_REUSEADDR so a previous run's TIME_WAIT does not break its setup; UDP incumbent does not enable reuse.
5. **FAILED**, exit 1. Same command as 03 with output/log prefix `05-native-loopback`.
   - `05-native-loopback.json`: sanitized ConnectionError frame points at the authorized SRT reader connection. Added bounded positive-reader connection retry based on MediaMTX's track-registration ordering. No claim about the RTMP results from 03–05, which were not retained as full matrices.
6. **RED**, exit 1. `PYTHONPATH="$PWD" OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 10 WORKTREE_t3-ae860af9/.tmp/m2/py311/bin/python .tmp/ingest-security/final_checks.py > .tmp/ingest-security/06-final-checks.log 2>&1`
   - One targeted unittest process: the existing two security tests plus one native test with separate loopback and Tailscale subtests. Both native probes are explicitly included in this sixth invocation, not reported as additional invocations. Not the repo gate.
   - `Ran 3 tests in 58.018s`; two security tests pass; two native subtests fail because RTMP positive media reads each returned zero.
   - Full independent host receipts: `06-native-loopback.json`, `06-native-tailscale.json`. Read them, not just the exit code.
   - No test/compile/native check run after invocation 06. Production source remained unchanged after that invocation started. Final read-through changed two secret-bearing dictionary lookups in `test_security.py` to `.get` so a missing generated username cannot appear in a KeyError; these two assertion-only changes were not rerun within the exhausted allocation. Parent's gate must cover that final test-file delta.

## Measured results and limits

Both final host receipts show:

- Exactly TCP 19450 plus UDP 18950, each bound only to its requested host (loopback in one receipt, 100.109.49.77 in the other), using child-specific inode proof.
- Both occupied-port startup attempts rejected and their children exited.
- Credentials absent from process environment/argv; both diagnostic fds `/dev/null`.
- **SRT**: all five publish denials pass; anonymous, phone and bad camera reads denied; valid phone camera/internal read receives three MPEG-TS messages; valid internal shielded/anonymous read receives three MPEG-TS messages. Camera publisher sent 150 H.264 packets; shielded publisher sent 16. Both publishers ended cleanly.
- **RTMP**: all five publish attempts that should be denied failed; phone camera publisher sent 150 H.264 packets, internal shielded publisher sent eight, both ended cleanly. However, authorized camera and anonymous shielded readers each returned zero packets. The three negative camera reader results are therefore **inconclusive as RTMP read ACL proof**, despite their true booleans. Do not promote the RTMP matrix to a pass.
- Each healthy final server exited 0, `server_stopped=true`.

Unresolved RTMP item: positive reader is attempted immediately after the first packet is handed to the muxer. My leading hypothesis is the same publisher-track readiness race fixed for SRT. MediaMTX RTMP `runPublish` accepts the publish action before `gortmplib.Reader.Initialize()` and `AddPublisher`; `runRead` immediately requests the path. This is an inference from primary source, not a measured diagnosis. Alternatives include RTMP mux/header buffering or another client-read behavior. `rtmp_read` currently suppresses errors into zero, so the receipt cannot distinguish them. Parent should preserve sanitized error categories/frame locations and establish a positive reader (bounded retry/explicit low probe limits are candidates) before claiming RTMP read ACL or runtime transport success. No speculative unverified fix was applied after the sixth invocation.

No remote phone peer, integrated engine/encoder, benchmark scorecard, correctness scorer, GPU workload, soak, performance timing, Twitch login/key lookup/ingest connection, or live stream was exercised. The Tailscale test is a local client connecting to the assigned Tailscale IP, not a second machine. Fixtures are existing BENCHMARK-ONLY derivatives; only their video packets were remuxed, no audio, no demo-ready claim. Parent owns the full gate and stream-path bench/scorecard acceptance after integration.

## Tools, licenses, hashes and primary sources

No installs, account/payment/waitlist requirements, CUDA/global config changes or metered API calls.

- MediaMTX v1.21.3, MIT. Existing parent binary measured SHA-256 `bfa372a169751bbf6da2ebddcbcd2f7d3ab3dca3cc553022162eda36fe03e73d`. Pinned release archive SHA-256 `0a2ea7eba96023631efa1bea7804823a9145b043b6646a8a05798d4ac24ed635` is inherited, not downloaded/re-measured here. Parent LICENSE exists beside binary.
- System libsrt 1.5.4 at `/usr/lib/x86_64-linux-gnu/libsrt-gnutls.so.1.5.4`, measured SHA-256 `30af7a9de19c8644f76fcb3f8c0b269bc48b98271deaca497cfdc6ff4ed099b6`. MPL-2.0 with BSD-3-Clause portions and other bundled component notices in `/usr/share/doc/libsrt1.5-gnutls/copyright`. This lane calls the existing library; no redistribution or copied third-party implementation. Public, free source: https://github.com/Haivision/srt/tree/v1.5.4 . The probe currently assumes this Linux x86_64 system library path; a fresh judge setup needs that public system dependency for this optional native probe. Production MediaMTX does not depend on this ctypes adapter.
- Parent PyAV metadata confirms 16.0.1 and BSD-3-Clause; reused without installing or modifying its environment. Parent `relay/requirements.txt` owns the existing wheel hashes and bundled FFmpeg license record. No ffmpeg command or GPU encoder executed here.
- No detector/model files were loaded or changed; no new model hashes to record.
- Source SHA-256 receipts for all six final code/test/script files are in `.tmp/ingest-security/source.sha256`. Patches relative to the authorized parent's source at inspection time: `mediamtx.patch`, `native-auth.patch`.
- MediaMTX auth/config defaults, exact path/recording fields: https://github.com/bluenviron/mediamtx/blob/v1.21.3/mediamtx.yml .
- SRT stream-ID parser: https://github.com/bluenviron/mediamtx/blob/v1.21.3/internal/servers/srt/streamid.go#L59-L88 .
- SRT authentication and registration ordering: https://github.com/bluenviron/mediamtx/blob/v1.21.3/internal/servers/srt/conn.go#L149-L268 .
- RTMP auth and registration ordering: https://github.com/bluenviron/mediamtx/blob/v1.21.3/internal/servers/rtmp/conn.go#L254-L330 .
- SRT C ABI option values/function declarations: https://github.com/Haivision/srt/blob/v1.5.4/srtcore/srt.h .
- SRT lifecycle and timeout semantics: https://github.com/Haivision/srt/blob/v1.5.4/docs/API/API-functions.md and https://github.com/Haivision/srt/blob/v1.5.4/docs/API/API-socket-options.md .

## Cleanup and parent integration

All commands completed. Final healthy servers were PIDs 3083751 (loopback) and 3085447 (Tailscale), each recorded exit 0; both `/proc` entries absent at final inspection. No `mediamtx` process appeared in the final comm-only inventory. Busy-port child exits are explicit booleans in both final receipts; all publisher threads joined and libsrt cleanup returned successfully. No owned process retained, no other session process stopped. Final test process exited 1 as reported.

Copy only the seven deliverable paths listed above. Scratch files are evidence, not final source; retain/copy receipts as the parent needs. Interface compatibility is retained for the parent runtime/live callers. The native probe's stricter RTMP acceptance deliberately remains red and should drive the next parent repair; do not weaken it back to one-packet success. Parent must rerun native transport evidence and its own full gate/required bench. No commit exists in this lane.
