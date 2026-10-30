# Local image-geolocation red team

The offline benchmark compares one licensed geolocation model on the same raw
and actually shielded video frames. **There is no measured red-team result yet.**
The first checkpoint establishes the model license gate and preregistration.
The private Mac environment, frozen-policy paired inputs, MPS execution and full
integration gate remain separate prerequisites. No dashboard geo-risk meter is
implemented: neither cost nor calibration has been measured.

## Model and license gate

The [official GeoCLIP code](https://github.com/VicenteVivan/geo-clip) is MIT.
The author's [weight release](https://huggingface.co/VicenteVivanco/geoclip-geolocation)
explicitly includes the trained weights and coordinate gallery, under its
[MIT license](https://huggingface.co/VicenteVivanco/geoclip-geolocation/blob/40a931123d2c6451ef7da1d37cf68cded0ec4d35/LICENSE).
This is the selected attack. Its fixed gallery contains coordinates, not
third-party training images. No training dataset is downloaded.

The pinned backbone is OpenAI CLIP ViT-L/14. Its publisher states that both
[code and model weights use MIT](https://github.com/openai/CLIP#license).
Its [model card](https://github.com/openai/CLIP/blob/main/model-card.md)
describes limitations and research intent. This benchmark is local, bounded
research on already licensed fixtures. It does not deploy a location service.

[StreetCLIP weights](https://huggingface.co/geolocal/StreetCLIP) and the
[PIGEON repository](https://github.com/LukasHaas/PIGEON/blob/main/LICENSE.txt)
use CC-BY-NC-4.0 and are excluded. No NC weights, gated model, paid endpoint,
account requirement or cloud image upload is part of this benchmark.

[The manifest](../models/geolocation-manifest.json) pins the official release,
backbone revision, every required asset hash and notices. Large-file hashes
come from official Hub LFS metadata and are verified against bytes before a run;
these binaries have not yet been downloaded or exercised. The reviewed adapter
targets GeoCLIP 1.3.0. Its private environment must retain a resolved dependency
lock, hashes and upstream license evidence for **every installed distribution**.
The runner rejects incomplete license closure or version drift. Package API and
Mac compatibility remain unverified until that environment is provisioned.

## Preregistration and input freeze

The private `out/w9/preregistration.json` records the selection before any
prediction. It selects frame 60, zero-based, from each coordinate-bearing tune
clip: three frames, six paired model attempts. Four other tune clips are
excluded because the saved source metadata has no GPS coordinate. Selection
uses metadata only. No reserved v2 metadata, locations or pixels are consulted.
The preregistration includes original/prepared clip hashes, source-page GPS,
evidence hashes, authors and licenses. Its raw/shielded PNG hashes are initially
null; **this is not a completed input freeze and cannot support a metric**.

Source-page GPS is approximate ground truth, not measured camera telemetry.
Each point carries a conservative analyst tolerance of 5 km. That radius is an
explicit analysis assumption, not a certified confidence interval. Frame-based
distance to the declared point and hit-rate sensitivity to that tolerance must
be reported together. Three tune frames from two US clips and one UK clip are
neither a representative sample nor a held-out evaluation.

The conductor/W1 must export exact corresponding lossless 1280×720 PNGs from
the frozen policy. This module does not generate masks or invoke a substitute
renderer. The exporter receipt names the source-frame index, prepared-clip
hash, actual shield input index, slate/video status, and actual frame hashes.
Top-level `policy`, `exporter` and `source_receipt` artifacts bind policy bytes,
the exporter source and its source/execution receipt. Each artifact is an object
with `path` relative to a supplied local root and `sha256`. `pairs` is an array:

```json
{
  "id": "<preregistered tune ID>",
  "frame_index": 60,
  "shield_source_index": 60,
  "source_clip_sha256": "<preregistered prepared clip SHA256>",
  "slate": false,
  "real_video": true,
  "raw": {"path": "<raw PNG>", "sha256": "<actual bytes>"},
  "shielded": {"path": "<actual policy output PNG>", "sha256": "<actual bytes>"}
}
```

The export producer must independently establish alignment, actual frozen
policy use and real video. Hashes bind its assertion to bytes; they cannot
prove the assertion true. A guessed mask, manual recreation, decorative
overlay or slate is not acceptable. An output that is held/slated at the
registered frame is a recorded eligibility failure; do not select a new frame.

Before predictions, freeze those artifacts once:

```bash
python -m bench.geolocation freeze \
  --preregistration out/w9/preregistration.json \
  --pairs out/w9/inputs/pairs.json --root . \
  --output out/w9/run-plan.json
```

Retain and timestamp that run plan's hash before submitting the MPS queue
packet. `freeze` refuses overwrites, missing/extra samples, misaligned indices,
altered hashes, slates and wrong PNG dimensions. No prediction should occur
until the conductor has audited the complete input freeze.

## Fixed attack and reporting

The attack ranks the entire author's pinned 100,000-row gallery by image versus
coordinate-embedding cosine similarity. It inserts no ground-truth anchors,
uses no country filter and does no city narrowing. Equal scores retain original
gallery order; repeated coordinate pairs are skipped when collecting the top
five. Coordinate features are encoded in batches of 512 to bound memory.
Actual memory, duration and Mac support remain unmeasured.

Preregistered metrics are top-1 and top-5 hits within 1, 25, 200, 750 and
2,500 km, plus mean/median top-1 great-circle distance to the source point.
The primary comparison is top-1 within 25 km. For point error `d`, uncertainty
`u` and threshold `t`, a hit is definite when `d + u <= t`, possible when
`max(0, d - u) <= t`. For top-k use the nearest of the first k predictions.
These bounds expose sensitivity to the stated tolerance; they do not certify
geolocation accuracy. Haversine distances use mean Earth radius 6371.0088 km.

Every selected sample has both arms in the result, including failed attempts.
A failure makes the primary metric and mean/median distances null for the
whole paired run. Exploratory hit bounds include that failed attempt as
unknown, `[0,1]`, in the original denominator. A missing or duplicate row is a
protocol error. Interrupted/setup-failed runs retain their append-only journal
and cannot produce a primary result. Do not silently rerun or omit a failure.

The inference command is `python -m bench.geolocation.run --help`. It requires
an explicit local release and backbone folder, a license-closed environment
receipt, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and a conductor EX-slot
receipt reference. The reference is bookkeeping, not a replacement for the
conductor's canonical Mac EX lease. The adapter refuses Linux or CPU/CUDA
fallback. All setup and inference go through root scheduling, with W1 Vision
judging first. The immutable exact queue packet lives under private `out/w9/`.

Produce the aggregate only after the run:

```bash
python -m bench.geolocation score \
  --preregistration out/w9/preregistration.json --plan out/w9/run-plan.json \
  --results out/w9/results.json --output out/w9/aggregate.json
```

Only the aggregate JSON is eligible for public use. Keep frames, per-frame
predictions, coordinates, candidate names, paths and journals private. Do not
use readable licensed natural images in the demo video or publish phone
images. A result from this small fixed attack does not establish anonymity:
landmarks, architecture, road layout and temporal clues can remain informative.

## Verification scope

`tests/test_geolocation.py` uses synthetic coordinates, byte fixtures and
temporary files. It checks distance wraparound, uncertainty/top-k arithmetic,
failure denominators, aggregate redaction, paired provenance, reserved-input
rejection and artifact substitution. It imports no model or imaging SDK.
These tests establish the protocol's behavior; they establish neither model
accuracy nor actual frozen-policy rendering correctness.
