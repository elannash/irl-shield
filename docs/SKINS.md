# Privacy skins

`shield.skins.SkinPainter` paints the supplied local binary rasters with
outward rounding and a six-pixel outside feather. The remaining choices are
exactly `frosted`, `bar`, `signed`, and `patch`. The CLI and session appearance
default to `patch`. Frosted remains an explicit selection; it failed the measured
720p30 runtime guard on the evaluated Linux host. See
[the runtime comparison](MASK-RUNTIME.md) for the measurements and limits.
The integration seam is `MaskRegion(left, top, raster, text_height)`, where
`raster` is a local uint8 array containing exactly 0 and 255. It must fit the
frame. The caller supplies the estimated text height in output pixels before
padding. Each call returns owned BGR pixels, the expanded opaque raster union
(`mask`), and the combined outside feather (`alpha`). Original frame and
rasters are not modified. Detection, upstream geometry, policy, scheduling,
and delay are unchanged.

## Outward rounding and feather

For a full rectangular raster with short side S, the radius is
`r = clamp(0.3 * S, 6, 24)` output pixels. Expand each side by
`ceil(max(r * (1 - 1/sqrt(2)), (2*r - S)/2))`, then draw the rounded rectangle
with radius r. The second term grows very tiny rectangles enough to fit the
diameter. Bounds are half-open pixel-square edges; samples are pixel centers
at half-integers. Round expansion outward and calculate the curve before
clipping to the frame. Thus original rectangular corners remain covered even
at the frame edge. Union the original raster back as a numerical safeguard.
Caller rasters extending outside the frame remain invalid; caller-clipped
rasters at the frame edge are supported without rounding inward.

Nonrectangular rasters grow by binary dilation with a Euclidean disk of the
same integer expansion radius. Never erode or open the original raster.
Islands and concave boundaries remain protected; this does not fill the
entire bounding rectangle. Empty rasters produce no paint.

Every opaque pixel has alpha 255 and actual skin paint. Outside the opaque
boundary only, distance d to the nearest opaque pixel center supplies
`t = clamp(d/6, 0, 1)` and `alpha = round(255 * (1 - 3*t*t + 2*t*t*t))`.
It reaches zero at six pixels; no inside pixel participates in the fade.
First compute every region's opaque union and maximum feather alpha. Then
paint feathers only outside that **global** opaque union. At an outside
feather overlap, the greatest alpha wins (supplied order breaks ties), so
alpha describes the actual source blend without stacking feathers. Opaque
extensions are drawn in supplied order, then the original raster paint is
restored in supplied order. An extension cannot displace another original
region's paint, and a feather cannot blend raw source into any region's
original or expanded opaque pixels.

The per-frame implementation keeps no raster-envelope or source-paint
cache. At most seven tiny binary disk kernels (radii 2–8, at most 17×17 bytes each)
are cached, independently of source pixels. Full rectangular rasters retain
the existing small precise-EDT corner, mirrored corners and integer-distance
straight edges. Bar and Patch union irregular rasters with the same dilation
radius before dilating each overlapping rectangle group: dilation distributes
over union, so the opaque result is unchanged. Colored skins retain individual
opaque rasters for resolving color ownership.

After the irregular opaque union is known, one precise distance transform per
overlapping six-pixel-expanded rectangle group supplies its outside feather.
Distance to a union is the minimum of the individual distances; the feather function is
monotone. Disjoint expanded groups cannot contribute positive feather to each
other. The original rectangular opaque and alpha fields are added afterward,
so rectangle corners retain their exact original construction. The
intended opaque geometry and alpha bytes are identical, including concavities,
islands, clipped edges and overlap seams; there is no proposed visual delta.
The existing 90 rectangular geometry comparisons remain unchanged. Owning
tests cover grouped irregular fields, caller-order material ties and visible
extensions whose original pixels were overwritten. Across all 150 saved SF
Market frames, the four optimized materials matched the previous rounded
painter byte for byte: 600 complete pixel, mask and alpha comparisons. This
is the tested population, not a universal numerical proof.

For Frosted and Signed, a temporary integer ownership map first resolves
opaque extensions in supplied order, then maximum-alpha feather ties in that
order, and finally all original rasters in supplied order. Only regions that
own an output pixel build material. The complete original averaging rectangle
is still used for every visible Frosted region; an occluded region can be
skipped because none of its output bytes survive. Per-region feather EDT is
needed only when a region's bounds intersect the global outside feather.
This preserves the original-paint restoration rule without retaining every
region's color array. The ownership map contains geometry, never source color,
and expires after the call. One native blend covers the touched bounds with
zero source weight on opaque protection, followed by an explicit opaque copy.

The initial light profile identified repeated irregular envelope and feather
work. It did not qualify runtime. The subsequent 150-frame render comparison
and native local guards, including raw queue limitations and failed attempts,
are recorded in [MASK-RUNTIME.md](MASK-RUNTIME.md). Patch is the default;
Bar and Patch are chat-votable. Frosted and Signed remain config-only.

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

The cell means become a grid. Native channel sums are divided by the exact
cell areas in float64 before float32 conversion, retaining the original
mean calculation. Bicubic interpolation upsamples the grid to four samples
per cell. A Gaussian with sigma two intermediate pixels gives approximately
half a cell of smoothing in output coordinates. A second bicubic interpolation
produces the final rectangle using independent channel kernels on the same
grid. The owning tests compare original-region uint8 paint against the
original interleaved calculation, including desaturation and fixed grain.

This bounded filter is an approximation to a full-resolution Gaussian, not
a full-resolution blur of the source. Grain in the range -2 to +2 is a
deterministic coordinate hash with a fixed seed. It never samples source
texture. Edge replication extends the original paint into the new opaque
envelope and feather; no new source sampling or fine texture is used. No
source pixels are blended back inside the global opaque union. All original
masked pixels have alpha 255, including corners, frame edges and concave seams.

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
regions. Its original paint is preserved and extended outward with the same
rounding/feather geometry as every other skin. No texture assets, manifest,
asset loader or runtime asset I/O is needed.

Existing NumPy and OpenCV dependencies retain their BSD-3-Clause and
Apache-2.0 licenses. No package or runtime service is added.

Both HOLD and PROTECT produce a full-frame opaque, source-independent field
for every selected skin. The safe presentation layer can replace this with
its slate. A skin swap is a single complete paint call; there is no fade
through unpainted video. Root must perform swaps before final egress and
retain all state/transport coverage gates.

## Chat voting

**Bar and Patch** are chat-votable, including moderator `!skin lock` commands.
Frosted and Signed did not pass the native runtime guard and cannot be selected
by chat. They remain available through explicit configuration/CLI selection.
Patch passed its current native guard. Bar is retained by the conductor on
its earlier passing receipt plus exact paint parity; the new Bar run literally
failed on two loop-seam PROTECT frames. This exception and the raw queue
limits are recorded in MASK-RUNTIME.md. New materials need a passing guard.

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

Votes are active in `(now - 60, now]`. Events before session start, expired
events, events more than 30 seconds ahead, and duplicate session IDs do not
count. Accepted future timestamps are clamped to receiver `now` for storage,
expiry and ordering, so forward clock skew cannot extend a vote or outrank
a later normal event. Each viewer has at most one active vote. A late older
vote cannot replace that viewer's newer vote in this normalized clock. Equal
normalized timestamps break by lexical event ID. IDs are retained for the
reducer's lifetime to prevent a replay with a changed timestamp.
Root must discard the reducer when its session ends.

The highest vote count selects a material unless a moderator lock is active.
A tie retains the incumbent when it is tied; otherwise lexical material order
breaks the tie. No active votes retains the incumbent, including an explicitly
configured material.
Votes continue to accrue and expire during a lock. Unlock immediately
applies the current votes. An older moderator command cannot reverse a
newer lock or unlock. The public snapshot contains only `skin`,
`skin_locked` and aggregate counts by skin; no viewer IDs or raw chat.
Root must call `snapshot(now)` periodically even when chat is idle to expire
votes and update the selected skin.

## Validation and queued work

Flat tests exercise exact-mean substitutions of high-contrast synthetic
text, concave rasters, overlapping unions, every skin swap, opaque coverage,
outward rectangular corners, tiny/clipped boxes, irregular dilation,
globally gated overlap feathers, rejected removed choices, source-independent holds, vote attacks,
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
frame copy, validation and mask union, and excludes startup caches,
detection, transport and encoding. No timing or OCR success is implied by
having these entry points. Root still must run the seven tune clips with
W1 geometry and the actual pipeline and retain its scorecard. Fresh-v2
pixels remain reserved and were not inspected by W5.
