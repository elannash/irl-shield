# Private local streamer dashboard

`shield.dashboard.DashboardServer` serves a phone-width controller over aiohttp.
It displays LIVE / PROTECT / HOLD, a fixed safe reason, session totals for unique
clue and face tracks, face mode, the current skin and votes, and local Hold / Resume.
The snapshot supplier owns unique session counting; per-frame box counts must not
be substituted. When stable identities are unavailable, supply `None` for the
corresponding total. The dashboard displays a dash and an availability note while
preserving current privacy status. A measured zero remains zero. No engine object
is serialized.

The optional location-risk display contains only a scalar and age. It never goes
through `presentation_fields()`, which supplies only W7's five safe fields.

## Root integration seam

Root constructs this object alongside the runtime, after validating its own
local ingest configuration:

```python
from shield.dashboard import DashboardServer, PairingData

dashboard = DashboardServer(
    host=dashboard_bind_address,  # literal 127/8, ::1 or 100.64/10 only
    port=dashboard_port,
    get_public_snapshot=get_public_snapshot,
    set_manual_hold=set_manual_hold,
    pairing=PairingData(local_rtmp_url, local_srt_url, srt_qualified=False),
)
await dashboard.start()
try:
    await run_relay()
finally:
    await dashboard.close()
```

The callbacks may return directly or be awaitable. They run on the dashboard's
asyncio loop. Root must marshal writes onto the engine's safe control boundary.
`set_manual_hold(False)` releases only `source='local'` (or the single chosen
manual source). It must never clear chat, Shield Mode, transport or egress holds.
Root retains stream/engine ownership and closes this service in its finalizer.

The required snapshot is a mapping with these fields:

```python
{
    'state': 'LIVE', 'reason_code': 'clear',
    'clues_hidden': None, 'faces_hidden': None,  # no session-stable IDs yet
    'face_mode': 'bystanders', 'skin': 'frosted',
    'votes': {'frosted': 3, 'bar': 1}, 'skin_locked': False,
    # optional pair: 'geo_risk': 0.35, 'geo_risk_age_s': 12,
}
```

The dashboard validates finite numeric ranges and enum fields. It drops unknown
keys and maps unknown reason codes to a fixed message. Invalid required fields
produce a fixed 503 and no exception text. Root must map runtime-specific reason
strings to safe reason codes. Skin IDs come from W5's shared registry; arbitrary
display names or user IDs are never accepted.

## Pairing and credentials

On every start the service generates a 256-bit random bearer token in memory.
Only `/dev/tty` receives the invitation URL. Missing controlling terminal aborts
startup and closes the listener. There is no stdout/log/file fallback. Do not tee
or capture the operator's terminal. Tokens are not CLI arguments or environment
values. The browser strips the fragment using `history.replaceState()` before
fetching any private content, then sends `Authorization: Bearer …`. It stores no
credential in cookies or browser storage.

The unauthenticated bootstrap has a token-entry form and generic assets only.
The dashboard HTML, snapshot, pairing JSON and QR PNG require authorization.
Every route rejects query strings, unexpected Host, and cross-site Origin or
Fetch-Site headers. Mutations require same-origin Origin and an explicit JSON
boolean; there is no cookie auth or CORS permission. Responses are no-store,
no-referrer, same-origin resources, and deny framing. Access logging is disabled;
callback exceptions return fixed messages without traceback logging. Root must
not add request/header/body logging around this app or log private objects.

Bind requires a literal loopback or Tailscale CGNAT address, never wildcard,
public address, LAN address or DNS name. Host must match the exact advertised
address and port. Use the Tailscale address for a phone: HTTP is carried inside
the tailnet tunnel, with access governed by the existing tailnet policy. This
module does not configure Tailscale, TLS, accounts or ACLs. Clipboard writes may
be unavailable on HTTP; select-and-copy remains available.

Pairing accepts only local RTMP(S)/SRT destinations. It never accepts Twitch
outbound credentials. Do not pass the Twitch stream key here. QR and import links
are private credentials too. They load only when pairing is expanded, are removed
on collapse/page hide, and never enter the public snapshot or presentation API.
The browser shows unqualified SRT honestly unless root explicitly supplies native
qualification evidence. URL limits keep QR size bounded; changing protocol never
changes or percent-encodes the supplied stream URL itself.

## Moblin source evidence

The official [README import specification](https://github.com/eerimoq/moblin/blob/22dd74423222001b242fc23921a91b0e366c88fb/README.md#import-settings-using-moblin-custom-url)
defines `moblin://?<URL encoded JSON blob>` and a `streams` array.
[`MoblinSettingsUrl.swift`](https://github.com/eerimoq/moblin/blob/22dd74423222001b242fc23921a91b0e366c88fb/Moblin/Various/MoblinSettingsUrl.swift#L54)
provides `name`, `url` and optional `selected` fields.
[`ModelSettingsUrl.swift`](https://github.com/eerimoq/moblin/blob/22dd74423222001b242fc23921a91b0e366c88fb/Moblin/Various/Model/ModelSettingsUrl.swift#L236)
decodes the URL query once, parses JSON and requests import confirmation.
[`CommonUtils.swift`](https://github.com/eerimoq/moblin/blob/22dd74423222001b242fc23921a91b0e366c88fb/Common/Various/CommonUtils.swift#L67)
uses the last slash-delimited RTMP component as its stream key. Accordingly this
module percent-encodes the outer JSON once, preserving the inner URL including
`?user=…&pass=…`. It emits only stream name/URL/selection, without auto-start,
remote control, chat/account credentials or platform configuration.

Upstream source inspection establishes format support, not a completed import
on a real phone. Moblin may retain imported settings on the phone. Treat imported
local ingest credentials as private and rotate them with the relay session.
No native SRT or phone UI has been tested in this workstream.

## Dependencies and verification

Existing dependencies: aiohttp (Apache-2.0), Pillow (HPND), NumPy (BSD-3-Clause),
OpenCV (Apache-2.0), and test-only PyAV/FFmpeg as documented by this repository.
Add `qrcode==8.2` to the shared pinned environment in root's integration change;
its BSD-3-Clause and inherited MIT notice are preserved in
`shield/dashboard/licenses/qrcode-LICENSE`. No third-party UI assets or images
are included. QR pixels are generated deterministically from private RAM data.

`tests/test_dashboard.py` uses generated data, real loopback HTTP, independent
OpenCV QR decode, existing Control and Renderer, and a lossless PyAV archive.
It proves the module's projection and renderer boundary, not future CLI wiring.
Root must additionally prove its callbacks never route private data to W7,
encoded frames, archive metadata or logs. Browser tests and synthetic mockup
receipts live under `out/w6/`. The full gate remains subject to conductor host
coordination; no native/GPU/held-out/performance results are claimed here.
