# Privacy skins

`shield.skins.SkinPainter` paints W1's supplied local binary rasters. It does
not detect, pad, round, feather or change a polygon. The default is `frosted`.
The integration seam is `MaskRegion(left, top, raster, text_height)`, where
`raster` is a local uint8 array containing exactly 0 and 255. It must fit the
frame. The caller supplies the estimated text height in output pixels before
padding. Each call returns owned BGR pixels, the exact raster union and its
opaque alpha plane. The original frame and rasters are not modified.

## Frosted information boundary

Frosted deliberately retains coarse color. Its pixels inside the mask depend
only on the following inputs:

- Each defined cell's BGR arithmetic mean, calculated with float64 sums.
- The mask raster, bounding rectangle and estimated text height.
- The configured desaturation amount and fixed spatial grain seed.

For a bounding rectangle of width W and height H, let
`minimum = ceil(max(24, 1.5 * text_height, max(W, H) / 4))`.
For each axis, `n = max(1, min(4, floor(size / minimum)))`.
Cell i covers `[floor(i * size / n), floor((i + 1) * size / n))`.
The two axis intervals form each rectangular cell. There are at most four
cells along the long axis. Every cell side is at least `minimum` except an
axis whose entire bounding rectangle is shorter than `minimum`; that axis
has one clipped cell. There is no small terminal cell.

Every pixel in these bounding-rectangle cells contributes to the mean,
including pixels outside an irregular polygon but inside its rectangle.
No pixel outside that rectangle contributes. This is a coarse-color
disclosure, not a claim of source independence. The cells partition the
rectangle with no gaps or overlap. `cell_extents()` exposes these exact
half-open extents for auditing.

The cell means become a grid. Bicubic interpolation upsamples the grid to
four samples per cell. A Gaussian with sigma two intermediate pixels gives
approximately half a cell of smoothing in output coordinates. A second
bicubic interpolation produces the final rectangle. This bounded filter is
an approximation to a full-resolution Gaussian, not a full-resolution blur
of the source. Grain in the range -2 to +2 is a deterministic coordinate
hash with a fixed seed. It never samples source texture. No source pixels
are blended back at the edge or elsewhere inside the raster. There is no
feather option in this initial renderer. All original masked pixels have
alpha 255, including edges and concave seams.

`desaturation=0.0` is the default. A value such as `0.65` partially mixes cell
means with BGR luminance. It can reduce recognizable color combinations,
but also makes the patch more visible. Coarse store colors can remain a
brand or place hint at either setting. Frosted's mean-preserving invariant
does not prove that these coarse colors or a very large isolated character
are safe. Independent OCR, attack views and geolocation review remain
separate acceptance requirements.

## Opaque materials

Every other skin is strictly independent of all source pixels inside every
mask, with alpha 255. `bar` is black redaction. `patch` is a fixed warm
neutral camouflage color; it never samples a surrounding ring. `signed`
is dark ink with an original small shield-shaped geometric mark on larger
regions, clipped to the exact raster. It adds no rounded corners outside
the raster. These choices preserve geometry rather than copying the
prototype's source-sampling Patch recipe or growing its Signed pills.

`petals`, `ripple`, `confetti` and `cloud` use four original imagegen-made
opaque pattern textures. They repeat in frame coordinates. The renderer
verifies asset SHA256 and opacity at construction and decodes each texture
once. Missing, corrupt, hash-mismatched or non-opaque textures select `bar`
and set `fallback_reason`. The painter performs no asset I/O during a frame.
Exact generation prompts, model availability, original output paths and
final hashes are in `fixtures/skins/attribution.json`. The built-in tool did
not expose an actual model identifier. Original generated assets are
distributed under CC0-1.0 as authorized by the fixture asset contract.
No external inputs were supplied to generation.

OpenAI's [content ownership terms](https://openai.com/policies/row-terms-of-use/)
assign output rights to the user to the extent allowed by law. The
[CC0 deed](https://creativecommons.org/publicdomain/zero/1.0/) describes the
project's asset dedication. This does not assert that generated output is
unique. Existing NumPy and OpenCV dependencies retain their BSD-3-Clause
and Apache-2.0 licenses. No package or runtime service is added.

Both HOLD and PROTECT produce a full-frame opaque, source-independent field
for every selected skin. The safe presentation layer can replace this with
its slate. A skin swap is a single complete paint call; there is no fade
through unpainted video. Root must perform swaps before final egress and
retain all state/transport coverage gates.

## Chat voting

Root creates a `SkinVotes(session_started_at)` reducer for each authenticated
EventSub session. It converts authenticated events to
`ChatEvent(id, user_id, frozenset(roles), text, timestamp)`. Only the existing
authenticated event path may supply `roles`; never derive roles from chat
text, display names or user-supplied fields. The reducer adds no OAuth scope
or network connection. Timestamps and `now` must use the same finite clock
domain. `now` must advance monotonically.

Commands are exact lowercase ASCII forms with single spaces:

- `!skin <name>` replaces the viewer's active vote.
- `!skin lock <name>` locks the output for a moderator or broadcaster.
- `!skin unlock` releases that lock for a moderator or broadcaster.

Votes are active in `(now - 60, now]`; events before session start, expired
events, future events and duplicate session IDs do not count. Each viewer
has at most one active vote. A late older vote cannot replace that viewer's
newer vote. Equal timestamps break by lexical event ID. IDs are retained
for the reducer's lifetime to prevent a replay with a changed timestamp.
Root must discard the reducer when its session ends.

Plurality keeps the incumbent on a tie. If the incumbent is not tied, the
lexically first tied name wins. No active votes retains the incumbent.
Votes continue to accrue and expire during a lock. Unlock immediately
selects the current plurality. An older moderator command cannot reverse a
newer lock or unlock. The public snapshot contains only `skin`,
`skin_locked` and aggregate counts by skin; no viewer IDs or raw chat.
Root must call `snapshot(now)` periodically even when chat is idle to expire
votes and update the selected skin.

## Validation and queued work

Flat tests exercise exact-mean substitutions of high-contrast synthetic
text, concave rasters, overlapping unions, every skin swap, opaque coverage,
missing/corrupt/cache-only assets, source-independent holds, vote attacks,
role controls and output-judge independence. Tests use only generated data.
Deliberate source-leak, viewer-lock and excluded-output-judge mutations must
fail the corresponding tests, then restore byte for byte and pass.

`bench.skins.judging.judge_output()` reads the complete painted output and
each region as original, contrast-stretched, sharpened, bicubic 2x and a
combined contrast/sharpen/2x view. Every credible output reading touching
the mask counts as a leak, including a same-family output judge. It retains
all raw judge readings. Primary input truth uses the existing registry's
family exclusions with no override and requires at least two actually
available independent engines. Masked-region crops can include unmasked
pixels outside an irregular polygon; box overlap conservatively counts
readings that touch the mask. A missing output box conservatively counts
as touching. Paint-only results never claim a video hidden fraction.

`python -m bench.skins.ocr_probe` is a synthetic OCR probe for the canonical
Mac queue. This explicitly labeled paint-only control declares the registry's
`vision-accurate` candidate. It does not describe the integrated W1 candidate.
The seven-clip integration must supply the actual frozen W1 registry
candidate/options to `judge_output`, without family overrides.
The probe requires explicit `--expected-python` and `--tesseract` arguments.
Before starting persistent Judges/Vision, it checks macOS/CPython3.11, the
exact isolated SDK, absence of overlays, dependency paths, CPU provider,
the dedicated mirror's executable Vision bridge and local hash-verified
models. Cache and receipt stay inside that mirror. Failures write a schema-1
receipt with stage/error/source hashes and exit nonzero. No dependency or
model is downloaded by the probe. EOF is an error, never a one-shot fallback.
`python -m bench.skins.cost` is the queue-only 1280x720, 24-mask,
30-fps-budget probe. It records all samples, median, p95, CPU seconds and
one-core CPU percentage at 30 fps. It exits nonzero if any requested skin
falls back or p95 exceeds 2 ms. It measures warmed paint calls, including
frame copy, validation and mask union, and excludes startup asset decode,
detection, transport and encoding. No timing or OCR success is implied by
having these entry points. Root still must run the seven tune clips with
W1 geometry and the actual pipeline and retain its scorecard. Fresh-v2
pixels remain reserved and were not inspected by W5.
