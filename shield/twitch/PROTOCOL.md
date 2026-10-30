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
every minute even when no event arrives; invalid authorization asserts a
latched connection hold and closes the socket. Startup/hourly validation is
required by Twitch. [Validation requirement](https://dev.twitch.tv/docs/authentication/validate-tokens/#who-must-validate-tokens).

The official endpoint is `wss://eventsub.wss.twitch.tv/ws`. Real reconnects
must retain this exact hostname over WSS; userinfo, explicit ports, fragments
and other hosts are refused. URLs are passed unchanged after validation.
HTTP and WebSocket redirects are refused. pyTwitchAPI handles network I/O,
ping/pong, keepalive reconnects, welcome migration and resubscription. The
owned hooks keep raw message IDs and enforce policy before library object
conversion. [WebSocket contract](https://dev.twitch.tv/docs/eventsub/handling-websocket-events/).

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
`shield_mode`, `local` and `twitch-connection` remain independent named holds.
Shared-chat origin messages are ignored. Commands are exact after trimming
and lowercasing. A stale resume cannot clear a newer hold; tied timestamps
favor holding. [Chat event fields](https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/#channelchatmessage).

UTC envelope timestamps enforce session start and a ten-minute age window;
engine hold times use monotonic time. The default ID capacity is 4,096.
Eviction advances a permanent timestamp floor rather than permitting an
expired ID to execute again. This deliberately rejects unseen late events
at/below the floor too. A future timestamp is rejected. This is bounded
in-memory protection for one adapter lifetime, not durable replay storage.
The server must preserve an ID's timestamp/content on redelivery. Never
recreate `ShieldEvents` just because a transport reconnects.

Startup, unexpected disconnect and shutdown assert a connection hold. A
welcome alone does not release it; subscriptions and reconciliation must finish.
An approved planned handover keeps accepting notifications on the existing
connection, adds no hold, and preserves the cache. The 30-second handover bound
or a failed handover faults into held unplanned recovery. The transport watches
for a closed socket rather than waiting for the library's keepalive retry.
Revocation latches for the adapter lifetime. Construct a new session after
owner reauthorization. The underlying `Control` is unchanged.

Startup and every unplanned recovery query Helix Get Shield Mode Status after
subscribing. An active result sets `shield_mode`; an inactive result updates that
source only if no newer Shield Mode event arrived while the request was in
flight. Only the connection hold is then released. A generation token prevents
an old request from releasing a later outage's hold. Requests fail closed and
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
