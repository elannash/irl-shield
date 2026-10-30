# Operator audio holds

Manual HOLD, authenticated chat HOLD and Twitch Shield Mode mute sound as well
as retaining the existing video HOLD policy. The operator source union is
`local`, `chat`, `shield_mode`, and the legacy `twitch-chat`/`eventsub` adapters.
Each source releases only itself. Reasserting a source keeps the hold active.
Detector PROTECT and automatic `transport`, `egress`, `twitch-connection` and
`twitch-reconcile` safety holds alone keep sound; they do not represent an
operator request to mute.

`RelayControl.hold` validates the source/reason, applies the hold under the
engine RLock, then advances an audio assertion epoch for operator assertions.
`RelaySession` checks the actual `Control._holds` source union under that same
lock. It discards incoming held audio and invalidates its entire buffered PCM
window on an assertion, including sound queued before HOLD. Releasing a hold
cannot replay those samples, even if assertion and release happen between two
presentation ticks. This intentionally loses some pre-hold buffered sound.
Production operator holds must use the runtime's shared `RelayControl`.

`RelaySession` selects PCM and stores its original epoch-bound guard together
under the engine lock, then releases the lock before invoking its public sink.
A blocking sink therefore cannot retain the lock needed by control or ingest.
Runtime binds the writer factory to that stored selection guard, rather than
sampling a newer control epoch after unlocking. Incoming audio can synchronize
the buffer epoch without replacing the guard for already selected PCM.

`EgressWriter` obtains the selection guard before taking its queue condition
and invokes guards after releasing that condition. It retains the original
guard through its one pending slot and onto `Egress.write`, which applies it
again immediately before encoder IPC. An active operator source or any
subsequent operator assertion silences that item, even after release. A newer
item selected after release can carry sound again. The guard takes the engine
lock only to select PCM; sink, native, IPC and network work occur after releasing
it. The runtime has one presentation caller; its guard factory is invoked only
after Session construction and PCM selection.

Sound already crossing the encoder IPC boundary, encoded, buffered in transport,
or sent to viewers cannot be retracted. The last guard is a pre-IPC snapshot;
an assertion racing with the ensuing IPC handoff can miss that handoff. This is
not a guarantee of instantaneous downstream silence. Local queues covered here
are not treated as already sent. This work does not qualify native Twitch
publication or walking privacy.

Synthetic regressions in `tests/m2/test_hold_audio.py` observe exact int16 PCM
through real session/control/writer code and the final Egress IPC boundary with
the native encoder replaced. Native encoder/recovery checks, benchmarks and the
full gate are held for the conductor; these functional tests do not claim their
coverage.
