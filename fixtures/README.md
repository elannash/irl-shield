# Licensed moving-video fixtures

`manifest.json` freezes clip IDs, source files, source SHA-256 hashes, excerpt
positions and the tune/heldout allocation. `ATTRIBUTION.md` lists authors and
license links. `evidence/` preserves the Commons API's source-page license and
authorship fields as checked during acquisition. No video is committed.

Prepare a clean cache:

```sh
python3 fixtures/prepare.py
```

This needs Python 3.11+, `ffmpeg` and `ffprobe`. Encoding uses `h264_videotoolbox`
on macOS and `h264_nvenc` on Linux. The corpus and independent judge cover
Latin-script text; footage uses US and European streets plus one Spanish street
in Mazatlán. This benchmark does not establish protection for other writing
systems. Originals must be at least 720p. Preparation verifies the complete
original's SHA-256, extracts a fixed five-second excerpt,
normalizes it to 1280×720 at 30 fps, and removes every audio stream. Source files
stay in ignored `cache/originals/`; muted prepared clips and receipts stay in
ignored `cache/`. HTTP errors report the server's retry interval and stop.

Verify an existing prepared cache without downloading or encoding:

```sh
python3 fixtures/prepare.py --verify-only
```

Use `--ids sf-market` to prepare or verify a subset. A cache copied to the Mac
needs only the processed `.mp4` files and generated `.receipt.json` files.
Originals are not needed when a processed clip verifies successfully.

The manifest's `sha256` records the provisioned NVENC excerpt. Different hardware
encoders can produce different bytes. A clean preparation therefore writes a
receipt containing the verified original hash, generated output hash, encoder,
and a recipe hash binding the exact excerpt position, duration, dimensions and
frame rate. Existing cache bytes must match either the canonical manifest hash
or that receipt; a mismatched or absent receipt fails verification. Receipts do
not change the frozen source or split.

`bench.synthetic.overlay(frame_bgr, frame_index, fps, seed)` adds four repeatable
text kinds: street sign, license plate, house number and storefront. It returns
a new BGR image and exact transformed text bounds in TL/TR/BR/BL order. Sign IDs
remain stable within each 4.8-second interval. The seed selects text, font,
size, rotation and perspective; time controls continuous motion and edge entry.
Fonts are bundled so generation does not depend on OS font lookup. An optional
`camera_offset=(dx, dy)` in pixels translates scene-attached signs and their
truth quads; the travelling plate keeps its independent path. Its default is
zero, preserving the original deterministic API output.

`visibility_fraction` measures the text quad's area inside the image divided by
its full area. `visible` means at least 30% is inside and the projected text
height is at least eight pixels. Partially visible text is still rendered and
labelled. Quads may extend beyond image edges. Natural text in the base footage
is additional detector material; synthetic truth labels only the added text.

## Benchmark assets versus demo assets

Every cached source, prepared clip, preview, contact sheet and benchmark output is
**benchmark-only, not demo-ready**. Street footage may retain readable third-party
brands or logos, including logos without text. Removing location text does not certify
brand removal. A demo asset must separately show no readable third-party brands or
logos and carry no music; use synthetic labels, street names or house numbers for a
clean before/after. This milestone does not certify any demo footage.
