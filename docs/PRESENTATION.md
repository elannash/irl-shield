# Viewer presentation

`shield.presentation` is a post-mask adapter. It owns the Caption badge and
three quiet slates. It does not detect text, paint text masks, connect to
Twitch, or read engine/control objects. Production wiring is a conductor task
after W1 releases the shared renderer fence.

The candidate defaults are Caption on and quiet slates. The owner can veto
the badge with `badge=False`. Privacy coverage is mandatory in a non-LIVE
state. The independent Opus Emil check and the owner's visual verdict remain
open. No default in the live CLI changes in this patch.

## Safe boundary

```python
from shield.presentation import PresentationRenderer, PresentationSnapshot, TrackTally

presentation = PresentationRenderer(width=1280, height=720, badge=True)
clues = TrackTally()
faces = TrackTally()

# Observe only stable IDs whose target masks actually reached a LIVE output.
# Keep face IDs in the separate faces tally.
clues.observe(applied_clue_track_ids)
faces.observe(applied_face_track_ids)
snapshot = PresentationSnapshot(
    state='LIVE', reason_code='none', clue_count=clues.count,
    face_count=faces.count, skin_name='frosted',
)
shown = presentation.render(masked_pixels, actual_mask, snapshot,
                            source_sequence=capture_serial)
# Send shown.pixels. Feed shown.mask into the existing area guards.
```

Create one renderer and two tallies per session. Use one presentation thread.
Use a new renderer for a resolution change. The frame must be 16:9 and at
least 160x90. Scale and glyphs are set up once. The intended view is 1280x720.
Pillow and NumPy are existing pinned dependencies; no new dependency is added.

The public snapshot has only `state`, `reason_code`, `clue_count`,
`face_count`, and `skin_name`. Unknown states, reasons, skins and malformed
counts fail explicitly. Counts are integers from 0 through 999,999,999. The
renderer never displays a reason string, face count or skin name. All slate
copy is fixed. Do not pass exception messages, stream URLs, QR data,
credentials, place names, or arbitrary dictionaries to this boundary.

States are `LIVE`, `HOLD`, `SHIELD_MODE`, `PROTECT`, `FAILURE`. Safe reasons are
`none`, `moderator`, `shield_mode`, `safety_check`, `transport`, `starting`.
Skins are allowlisted as `opaque`, `frosted`, `bar`, `patch`, `signed`; W5/root
can coordinate a deliberate allowlist extension if their final names differ.
`HOLD` with reason `shield_mode` selects the Shield Mode slate. A reason alone
never releases a hold. `PROTECT` and `FAILURE` select the failure slate.

The copy follows the design notes:

| State | Headline | Return line |
| --- | --- | --- |
| HOLD | Paused for privacy | Back when a moderator resumes |
| Shield Mode | SHIELD MODE ON | Back when Shield Mode ends |
| Failure | Paused while Shield checks this view | Back on its own once it’s safe |

## Counts and identity limits

Caption says `Shield hid N clues`. `TrackTally.observe` accumulates unique
opaque IDs across the session. Duplicate detections and re-entry with the same
ID do not increase it. It accepts bounded strings or nonnegative integers;
an invalid batch changes nothing. Face totals use a separate instance and
never enter the clue caption.

W1 must supply IDs stable for the session, including across exits and tracker
restarts. A recycled ID undercounts; a new ID for an old physical clue
overcounts. This is a unique-track total, not proof of physical-world object
identity. It has no geometric fallback. If W1 cannot supply that contract,
root must disable the badge. A future geometric counter would need the word
`estimate` in the viewer copy and an explicit limitations record. Never feed
boxes/frame, detector-call totals, or face boxes into `clue_count`.

## Privacy cuts and release ordering

Every non-LIVE frame immediately replaces the whole frame with a cached,
opaque slate. It does not sample the source. There are no entrance frames,
exit fades, breathing loops or state crossfades. This also supplies the
reduced-motion behavior for a single burned-in stream.

`source_sequence` is a session-monotonic capture serial, not a PTS, rendering
iteration, detector completion number or wall clock. While presenting a hold,
root must pass the ingress capture high-water serial, including frames still
buffered or in flight. The pixels on these calls are ignored. That advances
the privacy watermark through every pre-release capture. The first released
LIVE result must have a capture serial beyond that watermark, a newly checked
LIVE state and valid privacy masks. Reusing held pixels with a higher made-up
number violates the contract.

The watermark remains after release, so a pre-hold replay cannot appear even
after a good LIVE frame. An out-of-order HOLD covers immediately and blocks
through the greatest serial already seen. Root must re-read all active hold
sources at the final writer handoff. This module's frame serial guard cannot
substitute for the control/egress race protection.

## Audit geometry and performance

`Presentation.pixels`, `mask` and `overlay_mask` are owned arrays. A caller can
retain or mutate them without changing cached plates/slates. On LIVE frames,
the returned `mask` is the union of the incoming coverage and every pixel in
the opaque rectangular badge. `overlay_mask` contains that badge alone. On a
slate both masks cover the whole image. Never subtract decorative pixels
before running the actual output text-area guard. Face-area statistics remain
separate upstream; this adapter does not reclassify face pixels as text.

Glyphs, fixed words and all three full-frame slates are cached at setup. A
changed count assembles cached digit tiles; it never rasterizes fonts per
frame. Digits use fixed-width cells. The 720p scale uses 40 px caption and
return text and 60 px headlines. On a 390 px player these compute to 12.2 px
and 18.3 px. The contact sheet is a human review aid, not a legibility score.

The added-cost target is at most 2 ms/frame on a 720p workload with 24 masks.
Timing is **unmeasured** in this implementation hand-back. Root's immutable
EX-queue packet is `out/w7/queue-packet.json`; `benchmark.py` records every
sample, median, p95, maximum and exact source hashes. It measures only added
presentation work on an already masked synthetic frame. It cannot claim
end-to-end pipeline latency or detection quality.

## Verification and provenance

`tests/test_presentation.py` exercises two-random-source slate independence,
state swaps, immediate full coverage, fresh-LIVE ordering including replay
after release, opaque badge geometry, audit union, retained output ownership,
cached glyph use, safe field validation and session tally deduplication.
`out/w7/test-plan.md` records the realistic bug and owning boundary for each
case. A deliberate scene-sampling mutation must fail the independence test;
raw red/green logs remain under `out/w7/logs/`.

The renderer was authored in this Codex child. The Opus design files are
visual/copy references only. No prototype Python was read or copied. The
unmodified Atkinson Hyperlegible Next font is redistributed under SIL OFL
1.1 with its copyright and full license beside it. Exact font and asset hashes
are in `fixtures/presentation/ATTRIBUTION.json`. No external image, music,
real person or third-party brand is used. The contact sheet renders only
original flat-color synthetic verification geometry.
