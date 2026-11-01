# Verified Twitch egress and attended live mode

The Linux runtime uses one Twitch transport route: plain RTMP over
`127.0.0.1` to its own standard-library TLS forwarder, then verified TLS to
`live.twitch.tv:443`. PyAV never opens a direct Twitch RTMPS output. There is
no unverified fallback. The key remains in memory and crosses plaintext only
on loopback. No real Twitch connection or key was used to build these proofs.
Real ingest acceptance remains qualified only by the owner's attended
bandwidth test through this forwarder.

## Lifecycle and authorization

`relay/tls_forwarder.py` uses `ssl.create_default_context()` with system CAs,
`CERT_REQUIRED`, hostname checking and the ingest hostname as
`server_hostname`. It completes the TLS handshake before forwarding any RTMP
bytes. Its listener binds an OS-selected port on IPv4 loopback and survives
replacement encoder connections. It owns at most two connections and transfers
at most 64 KiB per read. Socket operations have bounded timeouts, and shutdown
closes owned sockets and joins owned threads. An RTMP EOF closes that connection
pair; old bytes are never replayed after reconnect. OS hostname resolution is
outside Python's socket connect timeout; a resolver stall can delay cleanup,
but cannot send RTMP bytes before verification.

`relay/runtime.py` owns the forwarder beside the existing writer. TLS failure
closes the loopback client, which becomes the existing `egress-write` error
and recovery state. Recovery stays fail-closed; it reconnects through the same
listener. OBS and Twitch still share the encoder/mux worker, so destination
failures are not isolated. Frames already inside native encoding cannot be
retracted; this change does not claim new HOLD timing or cadence qualification.

Publication flags are mutually exclusive. `--twitch-bandwidth-test` remains
the default explicit Twitch mode, with `?bandwidthtest=true`.
`--twitch-live` requires a fresh validation response for exact login `naie`,
matching client/broadcaster IDs, approved scopes and unexpired authorization,
then an exact `LIVE naie` confirmation on `/dev/tty` for that session.
The runtime consumes the single-use approval before creating any live route.
Omitting both flags retains authenticated controls without publication.
Live publication to the test channel requires an owner-started, attended session.
[RUN.md](RUN.md) contains the attended recipes; they are not local test commands.

## Loopback publication proof

`tests/m2/forwarder_probe.py` uses the actual `Egress`/PyAV encoder path and a
hash-pinned MediaMTX 1.21.3 TLS peer. It generates independent CA certificates
and original silent black H.264/AAC media. All listeners use loopback, and
MediaMTX's ancillary servers, including MoQ, are explicitly disabled.

The proof requires all four cases, in order:

1. Trusted CA and matching identity publish; MediaMTX logs the publication.
2. An unrelated CA produces an actual `SSLCertVerificationError`, an
   `egress-write` refusal/recovery code and no publication witness.
3. A mismatched hostname has the same verification/refusal/no-publication
   outcome. A test-only DNS resolver maps `mismatch.invalid` to the same
   loopback server; the TLS hostname still remains `mismatch.invalid`.
4. A new trusted publication succeeds after both negatives and the server
   remains alive. A dead server, timeout or unclassified failure is fixture
   error (exit 2), never a security pass.

A physical mutation disabling `check_hostname` and setting `CERT_NONE` makes
both negative cases publish and the proof exits 1. Exact source restoration
returns exit 0. The echo regression separately covers bidirectional data and
multiple successive connections through one listener.

From a provisioned checkout, coordinate with the host's performance queue,
then run the short functional proof under its shared lease:

```sh
scripts/host-lock shared .venv/bin/python tests/m2/forwarder_probe.py --out out/tls-forwarder-proof
```

The output directory must be new. Its `receipt.json`, MediaMTX log and process
receipt retain the publication witnesses, fixed failure codes and server exit.
Only synthetic identifiers are used. No detector, OCR judge, fresh heldout
clip, live ingest or real credential is involved.

The earlier `tests/m2/tls_probe.py` remains a deliberate diagnostic of the old
unverified PyAV path, restricted to a generated loopback peer. It is never the
runtime destination. Its negatives require attributable GnuTLS verification
diagnostics and trusted controls after the negatives; the dead-server regression
must exit 2. On the pinned insecure PyAV output API its expected full result is
still exit 1, not a passing security gate.

## Latency measurement

`tests/m2/forwarder_latency.py` runs only under the performance queue's inherited
exclusive lease. It compares the direct legacy **loopback-only** baseline with
the verified forwarder against the same local TLS peer. It uses the production
`Egress.write` interface, NVENC by default, 1280×720 synthetic moving pixels,
mono silence and a 30 fps source clock. The five paired repetitions alternate
path order. Each path has a separately reported initialization and three-second
warmup followed by at least 30 seconds steady state.

The receipt reports per-frame client-call median and p95 for each repetition,
the median of those five statistics, and the median paired delta. This includes
encoding, local IPC and mux-call cost. It measures client write-call overhead;
queued transport and receiver delivery are not timed, so it is not end-to-end
added latency or a new 720p relay/privacy gate. Queue receipts separately decide
whether load/pressure contamination qualifies the timing. Forced or contended
measurements remain explicitly diagnostic.

Queue the command in a fresh receipt directory after freezing the source:

```sh
scripts/perf-queue enqueue linux tls-frame-write --lane live-egress --priority 1 \
  --receipt 'out/tls-latency-{attempt}/receipt.json' -- \
  .venv/bin/python tests/m2/forwarder_latency.py --out 'out/tls-latency-{attempt}'
```

The runner, not this command, supplies and owns the exclusive lease. Do not
nest `host-lock` inside the timed job. CPU-only machines may explicitly choose
`--encoder libx264`; that is a different receipt and must be labeled as such.

## Other regressions and limits

The real runtime rejects missing or already-consumed live approvals before
opening a forwarder or encoder. Removing its `consume()` call fails that test.
The capture harness now also has cumulative drift that violates only the
absolute timestamp guard; deleting that guard fails even though every interval
is within 2 ms. Historical native receipts remain unchanged.

The unified Linux `scripts/check` covers functional tests and Python compilation.
Mac, Windows, real Twitch acceptance, real-phone walking, SRT, privacy quality,
A/V sync and final-source native HOLD timing remain separate qualifications.
No package/model installation was introduced. The forwarder runtime uses only
Python's standard library. Synthetic fixtures are CC0; tests reuse existing
PyAV 16.0.1 (BSD-3-Clause plus its bundled FFmpeg/GnuTLS component licenses),
MediaMTX 1.21.3 (MIT), NumPy/OpenCV pins and OpenSSL certificate generation
(Apache-2.0). Existing dependency/license inventories remain authoritative.
