# Owner-attended live session

This is a source-checked plan against `fb40e40`, not a runtime pass. The new
recipes below are **UNEXECUTED**. The conductor owns resource binding and any
future single native execution under the canonical exclusive lease. This
document allocates no execution budget and authorizes no publication.

The intended sequence is one complete 210-second prepared clip, then about
five minutes from the phone. The owner chooses W8b or the W8 fallback after
reviewing the pictures and privacy limits. The clip decision is pending.
These recipes stop and relaunch between segments, with fresh login, private
pairing and LIVE approval. Seamless clip-to-phone handoff has not been
qualified.

## Before choosing the clip

Keep Patch, accurate 4 Hz, accurate box floor 0.5 and fast 8 Hz. These recipes
use the existing Python 3.11 NVIDIA CUDA/NVENC path with its default 1-second
engine delay. They add no CPU mode, detector tuning or selective classifier.
Configured rates do not establish measured FPS or privacy.

W8b is a pan over stitched generated stills. Its review disclosed viewpoint
shifts around source frames 1171 and 5218 and reused pole texture. It is not
filmed walking footage. Reconstructing it requires NVENC and the exact cached
plates; the checkout alone does not contain those cached W8b pixels. Use an
already sealed source or let the conductor separately arrange reconstruction
under [DEMO-RENDERER.md](DEMO-RENDERER.md#w8b-opt-in-richer-source). These recipes
do not rebuild, re-encode or regenerate either clip.

The engraved NERALIN LANE plaque was observed readable and unmasked at source
frames 2088, 2400, 2700 and 3767 in saved output inspections. This is a known
frozen-detector limit affecting both providers, not a CPU-specific regression.
The owner may choose the fallback or use manual HOLD to cover uncertain
content, but HOLD is an operator action, not a detector fix. Neither option
earns a full privacy claim without review.

Earlier recordings, including fallback native25, had corruption and partial
source/output joins before the queue repair. They must not be shown as clean
video. The conductor reports that native26 with MediaMTX's 1,024-packet queue
cleared the local transport P0: its full 120-second steady window had 3,600
LIVE frames at 30 fps and zero PROTECT, HOLD or slates. Startup, drain,
unknowns and the failed clock guard remain separate. This historical local
result does not qualify full privacy, actual-phone ingest or phone-to-Twitch
operation. See [DEMO-RENDERER.md](DEMO-RENDERER.md) for the retained limits.

## Bind existing resources

Run commands from the repository root only after the conductor binds the
execution slot. `.venv`, `models/cache` and `.tmp/tools/mediamtx-v1.21.3` below
are repo-relative placeholders for an existing pinned Python 3.11 environment,
detector cache and verified MediaMTX installation. Replace them with the
provisioned directories when different. The launcher installs and downloads
nothing. NVIDIA wheel libraries, CUDA/NVENC support, free relay ports and room
for a full archive must already be available. Default ports are RTMP 19350,
RTSP 18554 and the existing unqualified SRT listener 18890; dashboard port 0
chooses a free port. Use RTMP for this session.

The launcher acquires the canonical EX lease or reuses its verified inherited
descriptor. A busy-host refusal is a stop, not a reason to bypass the lease,
kill another process or start a second publisher. The conductor supplies any
queue/resource wrapper. The two clip recipes are alternatives until the
conductor binds a run; never run them concurrently.

`out/prepared-w8b/source.json` and `out/prepared-fallback/source.json` below
stand for existing valid `irl-shield-w8-source-v1` JSON manifests beside their
sealed `source.mp4` files. A video filename is not a manifest. Each manifest
must describe all 6,300 ordered frames at 30 fps over 210 seconds and match
its video hash. Bind the actual prepared directories before execution.

Every `run-01` output below must be fresh and absent, including symlinks.
Choose a new name for every attempt, preserving failed evidence. Keep sender
receipts outside their relay archive. The 230-second runtime window allows
the full 210-second source plus startup and drain; an incomplete sender fails
acceptance. Never shorten or hard-loop the clip to fill a window.

## Local clip dry runs, no Twitch

Both commands are staged instructions only. `--local-only --host 127.0.0.1`
disables Twitch login, controls and publication. The real sender receives
runtime camera credentials in RAM and publishes once. It does not receive an
endpoint through argv. The demo path omits phone setup; its local dashboard
suppresses the private invitation announcement, so these commands do not
exercise attended dashboard pairing or a phone.

```sh
scripts/walk-linux --local-only --host 127.0.0.1 --venv .venv \
  --model-cache models/cache --mediamtx-dir .tmp/tools/mediamtx-v1.21.3 \
  --seconds 230 --demo-source out/prepared-w8b/source.json \
  --demo-receipt out/live-session/w8b-run-01/sender.jsonl \
  --archive out/live-session/w8b-run-01/relay
```

```sh
scripts/walk-linux --local-only --host 127.0.0.1 --venv .venv \
  --model-cache models/cache --mediamtx-dir .tmp/tools/mediamtx-v1.21.3 \
  --seconds 230 --demo-source out/prepared-fallback/source.json \
  --demo-receipt out/live-session/fallback-run-01/sender.jsonl \
  --archive out/live-session/fallback-run-01/relay
```

OBS on this host can read `rtmp://127.0.0.1:19350/shielded`. Show only the
shielded output. The sender's normal EOF ends publication once; it does not
switch inputs or stop the runtime immediately. Post-source protection belongs
in the whole-run census.

## Separate local phone and dashboard rehearsal

A physical phone cannot reach a listener bound to `127.0.0.1`. The following
loopback recipe exercises the existing private terminal/dashboard pairing
path with an attended local broadcaster UI. Any phone-shaped local fixture
must be labeled as such, not reported as a physical-phone rehearsal.

```sh
scripts/walk-linux --local-only --host 127.0.0.1 --venv .venv \
  --model-cache models/cache --mediamtx-dir .tmp/tools/mediamtx-v1.21.3 \
  --seconds 330 --archive out/live-session/local-input-run-01/relay
```

For a separately attended physical-phone local-only rehearsal, leave `--host`
and `SHIELD_BIND_HOST` unset so the launcher auto-detects its own Tailscale
IPv4 address. Both devices need their existing private connectivity. This
performs no Twitch login or publication and has not been rehearsed by this
documentation work.

```sh
scripts/walk-linux --local-only --venv .venv \
  --model-cache models/cache --mediamtx-dir .tmp/tools/mediamtx-v1.21.3 \
  --seconds 330 --archive out/live-session/phone-local-run-01/relay
```

Open only the current private dashboard invitation shown on `/dev/tty`.
Its fragment token authenticates private UI and API requests; keep it in the
private UI. A bare page is not paired. Expand "Pair your streaming app" and
use RTMP, either "Open in Moblin", its QR on another device, or the stream
URL copied directly into the broadcaster's private UI. Device import remains
unverified until the owner observes it working. The terminal's existing
private phone RTMP setup is the manual alternative. Keep every invitation,
QR, camera credential and activation URL off recordings, logs and receipts.
Never put them into shell arguments, documents or chat.

Use "Hold video" and "Resume manual hold" and observe the shielded output.
The dashboard clears only the manual hold. Hiding the page clears displayed
pairing material; a stale dashboard reports unknown state and is not proof
of current output. Shutdown ends the dashboard and its token. A new run
requires the new invitation and phone destination.

## Live clip, owner starts and approves

The remaining commands are **DOCUMENT ONLY**. Execute them only in an
owner-authorized attended session. Infisical supplies `TWITCH_CLIENT_ID` and
`TWITCH_BROADCASTER_ID` by name. The existing device activation URL appears
privately on `/dev/tty`; complete that login as the intended broadcaster.
Tokens and the runtime-fetched stream key stay in memory. No credential or
key is supplied in argv, environment overrides, logs or this document.

The current guard freshly validates the exact login `naie`, client ID,
broadcaster ID, scopes and expiry, then requires typing exactly `LIVE naie`
and Enter on `/dev/tty` for this runtime. A different login is refused.
Follow the actual printed prompt; never automate or persist approval.
`--twitch-bandwidth-test` connects to Twitch with `?bandwidthtest=true` and
is not live. The demo-source path rejects bandwidth-test mode. The earlier
attended bandwidth observation in [RUN.md](RUN.md) is not live-video or
phone qualification.

Bind `out/owner-chosen-source/source.json` to the owner's selected sealed W8b
or fallback manifest before using this recipe. Loopback suffices for this
prepared clip; it does not provide remote phone pairing.

```sh
infisical run -- scripts/walk-linux --twitch-live --host 127.0.0.1 --venv .venv \
  --model-cache models/cache --mediamtx-dir .tmp/tools/mediamtx-v1.21.3 \
  --seconds 230 --demo-source out/owner-chosen-source/source.json \
  --demo-receipt out/live-session/clip-live-run-01/sender.jsonl \
  --archive out/live-session/clip-live-run-01/relay
```

The live demo path retains the private dashboard announcement. Keep it off
stream and use manual HOLD if the owner elects to cover uncertain footage.
Do not start a phone publisher while the prepared sender owns `/camera`.
The relay rejects a second publisher; source EOF is not a supported hot-swap
API. There is no command here for replacing that input in place.

## Stop, relaunch, then about five minutes from the phone

Let the clip's bounded run finish, or use Ctrl-C for an operator abort. Wait
for the process and all its owned sender, engine, encoder, forwarder,
dashboard and MediaMTX resources to exit, and for the EX lease to release.
An abort or forced sender termination fails complete-clip acceptance. Preserve
the archive and failure; do not reuse its output paths. A relaunch creates a
gap in publication and fresh credentials, not a continuous stream promise.

Start the phone segment only after that cleanup. Leave `--host` and
`SHIELD_BIND_HOST` unset for automatic Tailscale address detection. The launcher
enables the existing phone setup and dashboard when no demo source is present.
Complete the new login
and fresh `LIVE naie` approval, open the new private invitation, and pair the
phone's RTMP broadcaster. Connect promptly for roughly five minutes of phone
input within the 330-second relay window, or stop earlier with Ctrl-C.

```sh
infisical run -- scripts/walk-linux --twitch-live \
  --venv .venv \
  --model-cache models/cache --mediamtx-dir .tmp/tools/mediamtx-v1.21.3 \
  --seconds 330 --archive out/live-session/phone-live-run-01/relay
```

Only the authenticated broadcaster or moderators may send `!shield hold`;
only the broadcaster may send `!shield resume`. The latter clears the chat
hold, not the dashboard/manual hold. Shield Mode, EventSub disconnect,
authorization revocation and transport recovery have independent holds.
Reconciliation or a resume action must not clear another source's hold.
HOLD overrides PROTECT, which overrides LIVE. If authorization is revoked
or state is uncertain, keep protection asserted and end the session rather
than bypassing it. Frames already in native encoding cannot be retracted.

Authenticated chat can vote `!skin patch` or `!skin bar`. The rolling window
is 60 seconds, with one current vote per user and the incumbent retained on
ties. Broadcasters and moderators can use `!skin lock patch`, `!skin lock bar`
or `!skin unlock`. Skin voting changes appearance, not detector policy or
HOLD authority. Local-only runs have no authenticated Twitch chat controls.

At the end, stop the phone broadcaster, then stop this relay with Ctrl-C if
the duration has not already ended it. Confirm owned processes exited,
listeners closed and the EX lease released. Do not kill other sessions or
reuse old camera URLs. A failed cleanup is unfinished work. OBS and Twitch
share one encoder/mux path; a destination failure can interrupt both. TLS
failure uses the existing verified forwarder recovery, never an unverified
route. See [LIVE-GUARD.md](LIVE-GUARD.md), [LIVE-EGRESS.md](LIVE-EGRESS.md) and
[WALK-LINUX.md](WALK-LINUX.md) for their existing boundaries.

## Fresh receipt before accepting a rehearsal

Retain a new receipt per attempt with the exact commit and a reproducible
command template, bound manifest identity, selected mode, timestamps, declared
observation windows and every failure. Use placeholders for private fields.
Never record or publish tailnet addresses or machine names, including in
command captures, shell history or receipts. Keep private terminal/UI contents
out of evidence. Check all of these:

- The sender ends with `complete: true` and 6,300 packets for a prepared clip.
  Retain its JSONL, `runtime.json`, `frames.jsonl`, `mediamtx.json` and every
  referenced encoded generation. The local checker emits `rehearsal.json`
  with `NOT CLEARED`; passing structural checks is not visual clearance.
- `runtime.json` ends stopped with no failure or cleanup errors. Record the
  effective lane providers, rates, threshold, encoder and delay. Independently
  decode the output before claiming measured FPS or clean pictures. Report
  whole-run and preregistered steady-window denominators separately, including
  startup, post-source output, missing arrivals, identity unknowns and every
  LIVE, PROTECT, HOLD and slate count. Never treat all-slate output as privacy.
- Preserve MediaMTX's queue size, warning counters, recent warnings/closes,
  diagnostic reader stop and `diagnostic_drops`. Empty retained warnings with
  dropped diagnostics do not prove warning absence. Inspect decoded joins,
  keyframes and the lower image for corruption; an encoder count cannot
  establish clean pixels. Inspect the plaque and stitching intervals as well.
- For local-only runs, confirm the selected mode, no authentication prompt,
  no Twitch publication and `runtime.json.verified_tls` null. The conductor's
  external-connection/process receipt must corroborate no Twitch connection;
  a null archive field alone is not network proof. Keep live and bandwidth-test
  evidence distinct from this local-only claim.
- Record owner-observed dashboard authentication, manual HOLD/resume and
  cleanup separately from authenticated Twitch moderator/broadcaster controls.
  Mark unexercised revoke/reconnect or phone behavior unverified. Preserve all
  failures and unknowns instead of replacing them with historical receipts.

The owner accepts the visual result and clip choice. Full privacy, real-phone
operation, native contention, A/V behavior and live delivery need their own
evidence; this docs-only preparation supplies none of those runtime passes.
