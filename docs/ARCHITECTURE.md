# IRL Shield engine architecture

The engine accepts timestamped BGR frames and local control events. It returns
masked pixels, the actual mask, coverage, state and presentation timing. It
owns the delay buffer, detector lanes, mask timeline, motion projection and
protection decisions. Transports own decoding, audio timestamps and encoding.
This keeps the engine a deep module: callers submit frames and poll due outputs;
they do not coordinate detectors or assemble privacy masks themselves.

## Adopted

A presentation delay `D` replaces synchronous detection on the frame clock.
The starting value is1.0s. Input frames retain their source indices and PTS.
A fast worker and an accurate worker each keep only their newest pending frame.
Slow inference therefore reduces detection coverage rather than blocking ingest.
Results carry their source frame index and completion time. A result completed
after a frame's deadline cannot retroactively justify that frame's coverage.

At each deadline, the engine considers results in `[i-B,i+A]`, projects their
quads into frame i, and unions the masks. Source rate, lane rates, widths, D,
B/A, coverage-age thresholds and padding are bench parameters. Apple Vision and
ONNX Runtime sit behind the same detector seam. Vision requests are reused per
persistent bridge, and ONNX records its actual execution provider. Portable
pipelines get preference when their measured privacy and speed are close.

Global motion is estimated once per input frame on a separate bounded worker.
The default is phase correlation at320px; ORB/RANSAC homography remains a measured
alternative. Quads preserve perspective when the selected transform supports it.
A failed transform is uncertainty, not identity. Local LK is deferred until
real-video evidence shows that global motion cannot meet the gate; the current
module's limits include independently moving objects and parallax.
The motion worker records completion time for every cached input transform.
Projection requires the whole path to have existed by the presentation deadline;
a late poll cannot retroactively turn late motion into covered LIVE output.

Coverage records the nearest fast and accurate result's frame age. Missing,
stale, late or unusable coverage enters PROTECT at the deadline. PROTECT uses
a single mean color, then escalates to a privacy slate if it persists. This
adapts the proposed heavy blur: Tesseract read a large protected house number
1842 at94% confidence from a20×11 preview. A1×1 down/up pass preserves no spatial
text shapes; all four positive-control labels became unreadable to the three judges.
An input gap also emits protection on the established source clock. A late input
frame is discarded and counted rather than replayed after its deadline.
The input buffer has a finite frame capacity; evicted input becomes a protected
gap. Each poll returns at most four frames by default, so an overdue clock
cannot allocate an unlimited batch or prevent a new HOLD between batches.

One explicit control module applies `HOLD > PROTECT > LIVE`. Holds are keyed by
source, so releasing one cannot clear another. It logs each transition's cause
and time. M1 uses a local trigger. Twitch chat and Shield Mode inputs belong to
M3; reconnect-command deduplication and TLA+ model checking belong to the announced
M2 formal-verification work. Their implementation has not been pulled into M1.

Rendering is an adapter after privacy decisions. Opaque convex-quad masks remain
the default. Rendering paints clipped ROIs into an owned output copy and mask,
with no full-frame NumPy boolean assignment. Retained outputs must remain owned;
reusing their buffers before the caller releases them would violate that contract.
Buffer pooling is deferred until transport ownership has an explicit lifetime.
A neutral optional badge can display the clue count; it defaults
off while the owner chooses the visual treatment on Friday. PROTECT and HOLD
pixels do not depend on that visual decision. No visual direction is locked by
this implementation.

## Qualification to the clock proposal

A presentation clock cannot by itself guarantee physical output throughput.
The renderer, encoder, OS scheduler or transport can still miss a deadline.
M2's measured SRT latency tail is a concrete example of downstream buffering
outside the masking engine. The bench therefore records actual emission and
encoded-packet receipts, frame completeness, PTS cadence and deadline misses.
It never reports a configured30fps timer as measured30fps delivery.

Source PTS are preserved. For a missing index after the first frame, its PTS is
inferred from the established source rate; the output is protected. EOF supplies
a terminal index so the clock does not invent an unlimited tail. Before the
first input establishes rate/shape/time, a transport adapter must remain on its
startup slate rather than assume a live picture.

## Seams and ownership

`ingest -> engine -> render -> egress` is the data path. File adapters drive the
bench. The local RTMP/SRT groundwork handles audio outside the engine and pairs
engine indices with original PTS. Control and later Twitch integration sit
beside this path. Neither the engine nor its detector adapters open network
connections or resolve Twitch credentials.

The historical synchronous runner remains under the bench solely to reproduce
the pre-clocked bake-off. It is not eligible for the revised gate. It can be
removed after the reference receipts are archived and all documented verification
uses the deadline engine. The tested M2 transport snapshot predates this interface
migration; its numbers remain historical evidence until its adapter is rerun.

## Verification and revised gate

TDD exercises the public engine, lane, motion and control/render interfaces.
Fault injection stalls each lane, drops input and cuts the scene during a stall.
A passing test
must show PROTECT or HOLD pixels at an uncovered deadline, never a raw LIVE
frame. Independent OCR still judges every scored output frame. Synthetic input
controls must demonstrate readability for every counted synthetic interval.

Gate1 now requires, on held-out: at least90% of natural intervals hidden,100%
of synthetic intervals hidden, the proposed masked-area ceiling, real video,
D<=1.0s, steady added-latency p95<=1.3s after warmup, sustained720p30 source-rate output and
protected frames<2%. Natural truth remains Latin-script text/digits observed at
input confidence>=.9 on at least2frames; one-frame-only natural text and non-Latin
coverage remain unproven. The held-out set is evaluated only after tune results
have margin, or at the milestone hand-back. The confirmed quiet measurement window
is02:00–03:00UTC October30. Performance receipts record startup separately, use at
least30s steady state, and reject warn/critical memory pressure. The final hand-back
follows the sustained receipt, no later than03:15UTC.

The later `shield login/run/replay/bench/doctor` CLI is a direction, not an M1
claim. Current setup and test commands remain scripts until that work is built.
