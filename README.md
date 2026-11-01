# IRL Shield

Published historical records use path placeholders: `REPO_ROOT` is the
repository root, `WORKTREE_<id>` identifies the original isolated checkout,
and `OWNER_HOME` is the operator's home directory. `OWNER_TMP` identifies the
original operator-specific scratch root; `RUNTIME_DIR` identifies the user
runtime directory, normally `/run/user/$(id -u)`. `<tailnet-ip>` means the
operator-selected Tailscale IPv4 address. Substitute local values for these
metadata placeholders before using a historical command. Executable scripts
use `$HOME` and UID-derived runtime paths. Historical proof JSON digest values
refer to original bytes at pre-scrub commit `8f12891db2e7347477bfd96329346ba9fd011231`.
The three maintained `SHA256SUMS` files instead identify current delivered
bytes with their original membership, excluding self-hashes. Regenerating those
manifests provides no new evidence that historical commands ran. Immutable v2
`fixtures/fresh-heldout-v2/nonreuse.json` retains its sealed bytes under the conductor's pre-public
exception until the one-shot completes; a later authorized change will record
the old and new hashes.

The repository privacy unittest in `tests/test_repository_privacy.py` scans
Git-tracked text, including symlink target text, for private owner paths and
Tailscale host addresses. It allows only the sealed ledger above. The complete
public policy CIDR `100.64.0.0/10` is permitted; bare host addresses are not.
The existing `scripts/check` gate discovers this test.

IRL Shield is an experimental privacy relay for IRL video. Its masking engine
looks for readable location clues and covers them before presentation. A delayed
frame clock gives asynchronous detector lanes time to work; missing coverage
produces a protected frame, and a local HOLD produces a slate.

The Linux integration command is `python -m shield.cli login|run|doctor`.
[Run instructions](docs/RUN.md) cover private RTMP phone ingest, OBS pull output,
memory-only Twitch authorization, EventSub controls and explicit Twitch publication modes. Native Twitch publishing is not part of local verification. SRT and
walking use remain unqualified; this is not a production relay.

**Twitch egress verifies its TLS peer.** PyAV sends RTMP only to a runtime-owned
`127.0.0.1` listener. A standard-library TLS forwarder connects to Twitch on
port 443 with system CAs, certificate verification and hostname checking.
There is no direct unverified RTMPS output route or fallback. The stream key
stays in memory and crosses plaintext only on loopback.

Twitch publication remains off unless selected explicitly.
`--twitch-bandwidth-test` is the default Twitch test mode; `--twitch-live`
requires fresh authorization as `naie` and an attended `LIVE naie` confirmation
each session. Start live publication only in an owner-authorized, attended
session. Omitting both flags keeps authenticated controls without publishing.
[Verified route and loopback proofs](docs/LIVE-EGRESS.md) document the limits:
real Twitch ingest acceptance still requires the owner's attended bandwidth
test, and privacy/walking qualification remains separate.

For a local attended terminal after setup:

```sh
.venv/bin/python -m shield.cli doctor
.venv/bin/python -m shield.cli run --local-only --host 127.0.0.1 --phone-setup
```

The bind address must be supplied with `--host` or `SHIELD_BIND_HOST`. Use
IPv4 loopback for local operation, or the detected Tailscale address for a phone, as described in [docs/RUN.md](docs/RUN.md). Credentials printed for
phone setup go only to the private terminal; do not capture or share them.

Run archives are off by default. Add `--archive <dir>` only when diagnostic
evidence is needed; a low-disk guard stops evidence without stopping the relay.

Gate 1 has not passed. Sustained timing is qualified on the M1 Pro and Linux,
including Linux CPU detection with libx264, but no tune policy meets all privacy
and real-video guards. The frozen held-out evaluation is queued separately;
[the hand-back](docs/M1-HANDBACK.md) distinguishes finished and pending evidence.

The engine accepts timestamped in-memory BGR frames independently of transport.
Apple Vision is available on macOS; PP-OCR models use ONNX Runtime on CPU, Core ML
or CUDA. Linux CPU/CUDA execution has been exercised; Windows remains untested.
The selected configuration and its hardware requirements will be recorded with
the final M1 scorecard. A configured 30fps source is never treated as measured
30fps output.

From the Linux checkout, the Mac wrapper synchronizes source and provisioned
assets, runs a bounded command and leaves all generated media out of git:

Run this reproduction after the overnight queues drain or are cooperatively
stopped; queued timing has priority over new quality work.

```sh
scripts/mac --seconds 14400 scripts/host-lock exclusive scripts/bench \
  --candidate vision-union --fast-candidate vision-rectangles \
  --split tune --run-id m1-reproduce-tune \
  --provider coreml --fast-provider coreml --static-model \
  --D 1 --B 6 --A 30 --fast-rate-hz 8 --accurate-rate-hz 4 \
  --fast-width 640 --accurate-width 1280 \
  --fast-limit-side-len 640 --limit-side-len 960 \
  --motion-mode phase --motion-width 320 --motion-min-response .05 \
  --padding .3 --encoder h264_videotoolbox \
  --warmup-seconds 10 --sustained-seconds 30 \
  --area-ceiling .15 --area-ceiling-basis bench/gate-1-policy.json
```

`scripts/bench` provisions hash-pinned fixtures/models and writes
`out/scorecard.json` plus an immutable run directory. This command includes the frozen diagnostic lane settings, proposed15% median
area ceiling and30-second sustained workload. Use a fresh run ID to repeat it.
It reproduces measurement and judging, not a passing policy: no tune candidate
passes all guards. Endpoint-only raw cards cannot claim gate1 until a closed
queue contamination receipt is joined. The one-shot held-out evaluation is
queued separately and remains reserved for the final milestone result.

Current counts, accepted/rejected timing receipts and limits are in
[docs/M1-HANDBACK.md](docs/M1-HANDBACK.md). The per-host overnight scheduler and
safe stop/report commands are in [docs/PERF-QUEUE.md](docs/PERF-QUEUE.md).

The measuring stick covers Latin-script text and Arabic digits observed by
Tesseract `eng`, Vision accurate `en-US`, and PP-OCRv5 English-mobile. Natural
truth requires input confidence at least .9 on two frames; output readings at
.5 can expose a leak. Every visible synthetic label counts. Non-Latin text,
natural text all input judges miss, and single-frame-only natural text remain
unproven. See [bench/README.md](bench/README.md) for the full scoring contract.

Fixtures are licensed CC0 or CC BY, attributed in
[fixtures/ATTRIBUTION.md](fixtures/ATTRIBUTION.md), and muted. They contain
third-party names and logos and are **benchmark-only**, including masked outputs
and previews. No current clip or still is designated demo-ready. Model weights,
download revisions, hashes and licenses are in
[models/manifest.json](models/manifest.json); candidate sources and portability
are in [bench/DETECTORS.md](bench/DETECTORS.md) and
[bench/PORTABILITY.md](bench/PORTABILITY.md).

Architecture decisions and qualifications are recorded in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Experiment history, including rejected
changes, remains in [bench/LOG.md](bench/LOG.md). Built in the owner-designated
Codex thread and its Codex children for the Codex x TwitchCon hackathon.
