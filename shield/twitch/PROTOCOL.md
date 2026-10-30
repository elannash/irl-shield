# M3 Twitch adapter, offline milestone

Access date: 2026-10-29 PT / 2026-10-30 UTC. All fixtures in `tests/m3/`
are synthetic. This milestone used no live login, Twitch HTTP request,
EventSub connection, stream key, ingest or personal OS keyring.

## Protocol decisions and primary sources

The app requests exactly `user:read:chat`, `moderator:read:shield_mode`, and
`channel:read:stream_key`. The user token belongs to the broadcaster; the chat
`user_id`, Shield Mode `moderator_user_id`, and stream-key `broadcaster_id`
all use that same ID. App-token chat requires additional bot permissions;
this adapter uses user-token WebSockets and requests none of them.
[Chat authorization](https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/#channelchatmessage),
[Shield Mode authorization](https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/#channelshield_modebegin),
[Get Stream Key](https://dev.twitch.tv/docs/api/reference/#get-stream-key).

Device authorization uses the public client flow, with no client secret.
Polling waits the returned interval before each request; an absent interval
defaults to five seconds and each `slow_down` adds five. Denial, expiry,
cancellation and other terminal errors stop polling. Twitch returns pending
errors in `message`; the RFC uses `error`; both are decoded without displaying
response text. Codes and activation URIs are secret-bearing values.
[Device flow](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#device-code-grant-flow),
[RFC 8628 §3.5](https://www.rfc-editor.org/rfc/rfc8628.html#section-3.5).

There is a documentation inconsistency: the general refresh page says only
authorization-code grants can refresh, while the device-flow section explicitly
describes public-client refresh and single-use refresh tokens. The owned adapter
follows the specific device-flow section and rotates the returned pair in RAM.
Friday's attended check must confirm the registered app is a public device-flow
client. No scope is added to resolve this inconsistency.
[General refresh page](https://dev.twitch.tv/docs/authentication/refresh-tokens/),
[Device-flow refresh details](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#device-code-grant-flow).

`UserSession` validates identity, client, scopes and lifetime at first use,
after refresh, and after an elapsed hour. `EventSubClient` checks the session
every minute even when no event arrives; validation HTTP 401 asserts a
latched connection hold and closes the socket. Temporary validation failures
hold and retry through normal reconciliation. Startup/hourly validation is
required by Twitch. [Validation requirement](https://dev.twitch.tv/docs/authentication/validate-tokens/#who-must-validate-tokens).

The official endpoint is `wss://eventsub.wss.twitch.tv/ws`. Real reconnects
must retain this exact hostname over WSS; userinfo, explicit ports, fragments
and other hosts are refused. URLs are passed unchanged after validation.
HTTP and WebSocket redirects are refused. pyTwitchAPI supplies socket I/O,
ping/pong, the keepalive watchdog and planned welcome migration. Owned hooks
retain receive provenance, bound and retry connection attempts, and recreate
subscriptions from verified current-session responses. They keep raw message
IDs and enforce policy before library object conversion.
[WebSocket contract](https://dev.twitch.tv/docs/eventsub/handling-websocket-events/).

## Interfaces for root integration

Root owns CLI, root requirements and egress. Install `-r shield/twitch/requirements.txt`
into its existing Python 3.11 runtime. No new account is needed for offline tests.
Real app registration/login is owner-attended work, outside this milestone.

Compose the following inside one caller-owned `aiohttp.ClientSession` lifetime:

```python
client_id = os.environ['TWITCH_CLIENT_ID']  # injected by infisical run --
http = TwitchHTTP(http_session)
auth = DeviceAuth(client_id, http)
tokens = await auth.login(owner_terminal_prompt, cancel_event)
user = UserSession(auth, tokens, broadcaster_id)
events = ShieldEvents(broadcaster_id, engine.hold)
client = EventSubClient(user, events, allow_live=True)
try:
    await client.start()
    key_provider = HelixKeyProvider(user, http)
    # Pass key_provider to the M2 in-process egress adapter.
    await stop_event.wait()
finally:
    await client.stop()
```

Imports are from `shield.twitch.auth`, `.http`, `.storage`, `.events`,
`.transport`, and `.keys`. The example is a root wiring recipe, not a CLI
that currently exists. Do not run it before the approved attended session.
Launch the eventual root command via `infisical run -- <root command>`;
never provide a client ID, code, token or key as a command-line argument.
An existing `Control` can also be used by adapting `hold(..., now=...)` to
`control.set_hold(..., at=...)`; `engine.hold` already matches directly.
Wire the same engine instance used by M2. Do not create another control machine.

`KeyProvider.get_key()` is async and returns a redacted `Secret`; M2 reveals it
only at the final in-process network seam. This module creates no stream URL,
subprocess, serialization or egress. Bandwidth-test mode remains M2/root's
responsibility; no live egress is authorized by this module.

RAM is the default. `TokenStore` is constructed only for root's explicit
`--remember`; `save(..., remember=True)` permits an OS keyring write.
The only automatic backends accepted are macOS Keychain, Windows Credential
Vault and Linux Secret Service. There is no plaintext fallback. `load()` forces
refresh because monotonic deadlines cannot survive a process restart. Root
must save the latest rotated pair when opting in; a crash before saving a
single-use refresh token may require a fresh attended login. Tests inject an
in-memory mock; personal backends were not exercised.

`owner_terminal_prompt` writes the activation URL only to `/dev/tty`, with
no browser subprocess or stdout/stderr output. Run it only from a private,
unrecorded owner terminal. A terminal transcript recorder would still capture
terminal output; the function cannot defeat a recorder. No prompt was opened
in this milestone. Windows needs a root presenter for its owner console.

## Control policy and limits

Only a matching broadcaster ID or a Twitch-provided moderator badge can
assert chat hold. Display names and broadcaster badge text grant no authority.
Only the matching broadcaster ID may resume, and resume clears `chat` only.
`shield_mode`, `local`, `twitch-connection`, and the internal `twitch-reconcile`
guard remain independent named holds.
Shared-chat origin messages are ignored. Commands are exact after trimming
and lowercasing. A stale resume cannot clear a newer hold; tied timestamps
favor holding. [Chat event fields](https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/#channelchatmessage).

Authorized chat holds and Shield begins apply in every phase, even from an older
connection generation, and are never dropped for timestamp reasons alone.
Holds and releases order by their raw Twitch timestamps, with no local-clock
clamp or receipt-time fallback. A parseable hold keeps its raw ordering stamp
even when it predates policy start, is expired, or is far ahead of local time.
Older and equal releases cannot clear it. Local time is used only for freshness
and replay bounds. Releases require the current live READY generation, aware finite timestamps,
the session-start/ten-minute replay floor, and strict source ordering. Releases
allow at most 30 seconds of forward skew. That bound is a local engineering choice;
the inspected Twitch WebSocket references define RFC3339/nanosecond UTC timestamps
but give no host-clock tolerance. A release beyond that allowance stays rejected
under HOLD and logs the fixed warning `clock-skew`, with no timestamp, actor,
message text, URL, code or credential in the record. There is no deferred release:
the owner must send a fresh command when clock/freshness checks permit it.
[Timestamp and redelivery fields](https://dev.twitch.tv/docs/eventsub/websocket-reference/).

A missing, naive or unparseable hold stamp uses a strict barrier at the highest
valid Twitch timestamp observed so far. A release at or below that barrier stays
HOLD; a greater fresh stamp can release immediately. With no timestamp history,
the barrier is pending: the first valid observed stamp establishes it before
its event can release the hold, and a later strictly greater fresh stamp is
required. Host receipt time never guesses the hold's ordering time.

`EventSubClient` feeds every received message's `metadata.message_timestamp`
through the policy's public `observe_timestamp(metadata)` method before dispatch,
including welcome, keepalive, reconnect and the welcome consumed during planned
handover. It does so on the owner loop. Missing/invalid metadata does not advance
the watermark. Valid notification envelopes also observe timestamps before chat
command admission; ignored ordinary chat can advance the watermark without
consuming dedup memory. Direct/custom transports must preserve that observation
seam. An active Helix reconciliation result creates the same missing-stamp Shield
barrier. Authoritative subsequent status results still obey query identity and
Shield revision fences; they remain separate from EventSub end-event ordering.

Engine hold times use monotonic time. The ID cache defaults to 4,096 entries.
An ID still remembered is deduplicated. An evicted protective ID may conservatively
reassert a hold; an expired release cannot replay through the permanent timestamp
floor. This is bounded in-memory protection for one adapter lifetime, not durable
replay storage. It assumes redelivery preserves content and timestamp. Never
recreate `ShieldEvents` just because a transport reconnects.

Startup, unexpected disconnect and shutdown assert a connection hold. A
welcome alone does not release it; subscriptions and reconciliation must finish.
An approved planned handover keeps accepting notifications on the existing
connection, adds no hold, and preserves the cache. The 30-second handover bound
or a failed handover faults into held unplanned recovery. The transport watches
for a closed socket rather than waiting for the library's keepalive retry.
Only definitive validation HTTP 401 latches invalid-token revocation; network,
5xx and claim-validation failures remain held and retryable. An unreadable 401
body cannot turn that status into a transient error. Relevant EventSub revocations
also latch. A revocation before startup finishes settles `start()` with
`TwitchError('EventSub startup authorization revoked')`, closes its transport,
and keeps HOLD latched. Transient startup faults continue held retries.
Construct a new session after owner reauthorization. The underlying
`Control` is unchanged.

Every socket-driven policy call marshals onto the owner loop. The reader captures
the generation of the socket it read before dispatch, rather than looking up the
latest generation when an old callback runs. Public policy methods additionally
serialize under an RLock. Welcome/query/release require the matching live session
and generation; each reconciliation also has unique immutable token identity.
No connection hold releases until all three subscription responses confirm enabled
status, distinct IDs, matching conditions and the current session ID. Failed or
partial subscriptions retry missing topics under HOLD. An expired 20-second dial
attempt stays inside the retry boundary, leaving watchdog and reader tasks alive.

Startup and every unplanned recovery query Helix Get Shield Mode Status after
subscribing. An active result sets `shield_mode`; an inactive result updates that
source only if no newer Shield Mode event arrived while the request was in
flight. A second internal guard remains held while the connection source releases,
so callback-reentrant faults cannot expose a transient LIVE state. Reentrant Shield
begin during status application is reasserted before either guard releases. The
generation/session/query identity prevents old results releasing a later outage.
Requests fail closed and
retry after 1, 2, 4, 8, 16, then 30 seconds (bounded backoff); HTTP itself has a
20-second timeout. The existing approved `moderator:read:shield_mode` scope covers
the query, with broadcaster ID used for both broadcaster and moderator parameters.
[Get Shield Mode Status](https://dev.twitch.tv/docs/api/reference/#get-shield-mode-status).

Twitch exposes no chat-history/catch-up interface for commands missed during an
outage. The adapter does not invent or recover those commands. Video is already
held throughout that window; after recovery the snapshot reconciles Shield Mode
and existing chat/local holds remain intact. This absence is based on the current
[chat interface](https://dev.twitch.tv/docs/chat/) and
[API reference](https://dev.twitch.tv/docs/api/reference/), with historical confirmation
in the [Twitch developer forum](https://discuss.dev.twitch.com/t/missing-message-when-the-bot-is-disconnecting/37911).
The forum answer is historical community evidence, not a new Twitch API guarantee.
The offline tests establish event/control behavior. Actual ingest, live
authorization, TLS, genuine moderator delivery, the Mac and Windows remain
unverified here.

## Offline receipts

Run the M3 suite from the checkout with its root on `PYTHONPATH`:

```sh
nice -n 10 <python311> -W error::ResourceWarning -m unittest discover -s tests/m3 -v
```

The test requires the pinned Twitch CLI binary at
`.tmp/tools/twitch-cli_1.1.24_Linux_x86_64/twitch`; download/install instructions
and hashes are in `LICENSES.md`. Python sockets are guarded against nonlocal
connections. All mock HTTP/WebSocket listeners bind IPv4 loopback. CLI's
internal RPC uses fixed port 44747 and binds wildcard in upstream code; the
test refuses to start when another session owns that port and stops its own
process. The CLI subprocess uses an absent scratch config and `--no-config`.

CLI v1.1.24 has no chat generator and rejects chat subscriptions. The CLI test
uses a local facade only for the synthetic chat-subscription response, and
forwards Shield subscriptions and initial WebSocket bytes to the actual CLI.
After CLI-requested reconnect, pyTwitchAPI connects directly to the new CLI
session. The separate localhost fixture server exercises real transport chat
commands, roles, deduplication and revocation. This distinction is intentional;
the CLI check does not claim to test chat generation.
[Official CLI test contract](https://dev.twitch.tv/docs/cli/websocket-event-command/),
[Pinned topic validation source](https://github.com/twitchdev/twitch-cli/blob/v1.1.24/internal/events/websocket/mock_server/manager.go),
[Pinned trigger source](https://github.com/twitchdev/twitch-cli/blob/v1.1.24/internal/events/trigger/trigger_event.go).
