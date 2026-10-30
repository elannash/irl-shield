# Archive comparison renderer

`python -m tools.demo_renderer` writes a silent MP4 with the fictional raw
source beside the actual decoded archive output, a PNG poster, and a JSON
timeline. It never runs a detector, connects to Twitch, reads a phone feed,
or measures performance. Use the existing Python 3.11 environment with PyAV,
NumPy and Pillow. No dependency or model download was added.

## Safe source requirement

Every export requires an explicit source manifest and its SHA-256, plus the
archive sidecar and its SHA-256. There is no fallback to arbitrary archive raw
pixels. The source must declare `origin: wholly-synthetic`, `demo_ready: true`,
a CC0, CC-BY or public-domain license, and a named public-asset reviewer who
checked fictional text, no real people, no brands/logos, and no music. A
licensed natural street with synthetic labels does **not** qualify. Neither
phone footage nor held-out fixtures qualify. These pins check integrity;
they do not independently prove the reviewer's claims. Inspect the actual
source before approving its manifest for a public video.

The bundled fictional street is generated in this Codex child. Its exact
prompt, model ID `not exposed`, original hash, normalized hash, visual review,
and font licenses are in `fixtures/demo-renderer/ATTRIBUTION.json`. The
project dedicates its generated scene and fictional-sign composition to CC0.
The font retains its bundled license. Root must merge that manifest into the
canonical fixture attribution when integrating this workstream.

## Synthetic layout preview

```sh
python -m tools.demo_renderer.sample --output out/demo-synthetic
```

This creates a short repeated-still fixture with fictional `Cedar Vale` and
`142` signs. The fixture has programmatic masks and **fabricated illustrative
detector receipts**. It is suitable for checking the export layout and the
reader's rejection paths, never for claiming native detection, tracking,
readability, latency, throughput, or real-time execution. The preview carries
`SYNTHETIC TEST / OFFLINE` on every frame. The command prints the two hashes
also saved in `out/demo-synthetic/pins.json`. Paste those exact hashes:

```sh
python -m tools.demo_renderer \
  --archive out/demo-synthetic/archive \
  --source-manifest out/demo-synthetic/source.json \
  --manifest-sha256 <source-manifest-sha256> \
  --evidence-sha256 <archive-demo-evidence-sha256> \
  --output out/demo-synthetic-test-offline.mp4
```

The MP4 contains only video. Existing outputs and companion files are never
overwritten. Files stay in temporary scratch until all media identity checks
and the encode complete. The command removes its scratch on failure.

## Archive and evidence contract

The current writer at `relay/stream.py` records `frames.jsonl`, `encoded.flv`,
and later recovery generations as `encoded-g0002.flv` and so on. Each row
contains `egress_generation`, engine `index`, original floating source `pts`,
`deadline`, `presented_at`, state/protection flags and the actual packed mask.
Its `pixels_sha256` is the **pre-encode BGR** hash, so it cannot authenticate
lossy decoded H.264 pixels. The renderer instead pins each whole encoded file
and matches exact decoded rational PTS to an explicit mapping.

The writer does not currently retain source frames, capture-origin records,
detector receipts, or receipt-to-paint associations. Old archives lacking
those fields fail closed. The renderer does not reconstruct them from
coverage ages, output appearance, network PTS, or `round(networkPTS * fps)`.

`source.json` has schema `irl-shield-demo-source-v1`:

- `origin`, `demo_ready`, `license`, `public_asset_review` as described above.
- `fps` as a positive rational string for the final frame's duration.
- `video: {file, sha256}` with a local relative file path.
- `frames` in strict source order, each `{index, pts, pixels_sha256}`.
  `pts` is an exact rational string; `pixels_sha256` hashes decoded RGB24.
  Engine indices must be supplied by capture, never calculated from PTS.

`archive/demo-evidence.json` has schema `irl-shield-demo-evidence-v1`:

- `source_manifest_sha256`, `frames_sha256`, and
  `encoded_files: {"encoded.flv": "<sha256>", ...}` pin the inputs.
- `evidence_kind` is `synthetic-test` or `measured-native`.
  `execution_mode` is `offline` or `real-time`. The sample generator only
  writes `synthetic-test` and `offline`. A measured-native sidecar must come
  from the actual recorder described in the integration proposal, with its
  sealed source/model/run evidence retained separately by the conductor.
- `capture_origin_monotonic` is the actual capture stamp of the first source
  frame, in the **same monotonic clock domain** as detector completion and
  presentation deadlines. Retain those original stamps across recovery.
- `frames` aligns one-for-one with archive rows. Each contains
  `{egress_generation, index, source_index, captured_at_monotonic,
  encoded_file, encoded_pts, applied_receipt_ids}`. The two indices must
  match the source/engine identity. `encoded_pts` is a rational string
  observed by the archive finalizer, not inferred from a network clock.
- `detections` contains `{id, lane, source_index, completed_at_monotonic,
  status, quads}`. Lanes are `fast` or `accurate`, status must be `ok`, and
  nonempty finite quadrilaterals are required for every applied receipt.
  Applied IDs must name the actual receipts whose projections contributed
  to that frame's archived mask. Completion must fall on or before that
  frame's deadline and after the detector source's capture stamp.

The current strict format requires a complete ordered source/output mapping,
including detector source frames. Export a complete bounded segment; sparse
or missing captures are rejected. One video stream per input is supported.
Relative paths must stay inside their manifest/archive directory.

## Timeline meaning

Each mask cell corresponds to an actual archive mask whose unpacked SHA-256
matches the writer's `mask_sha256`. An amber cell has an applied detector
receipt from a **later source frame**, proving a backward paint association
when the recorder is authentic. Green means another masked frame. HOLD and
PROTECT retain their actual archive state; they do not invent detector
receipts. Detector ticks show the recorded completion times relative to the
capture origin. The two rows share that capture clock. The poster prints
the first detector-mask time and first applied confirmation time.

The JSON preserves all original source identities, deadline/presentation
offsets, receipt IDs, and detector completion stamps. Native performance is
`null`. Video playback rebases only the export's presentation PTS to zero;
it preserves all source PTS differences exactly on a 90 kHz clock and rejects
unrepresentable timestamps. It never rebases engine identities.

## Verification and remaining proof

`python -m unittest discover -s tests -p 'test_demo_renderer*.py' -v`
exercises unsafe/missing provenance, wrong hashes/identity, missing detector
receipts, capture-origin mismatch, late confirmation, tampered masks,
nonzero source PTS, backward-frame associations, silent MP4 encode/decode,
and rejection without publishing partial output.

The W8 hand-back retains source hashes, all invocation attempts, the
synthetic preview and raw logs. The full SH gate is pending root scheduling.
Real detector/native-relay recording, model/NVENC execution, and the
independent Emil review remain unverified. Source instrumentation must be
integrated after its fence releases, then the conductor queues native work
with its literal argv and immutable source/model/asset hashes. No held-out
or natural footage is needed for that proof.
