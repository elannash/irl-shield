# Fresh heldout v2 preparation

The dataset is **frozen-ungraded**. All three new Commons sources have a natural
and synthetic variant. Each of the six videos has been decoded and verified as
150 zero-origin CFR30 frames at 1280×720, with no audio. Original, derived and
truth hashes, licenses, revisions and recipes are bound in the immutable
[manifest](../fixtures/fresh-heldout-v2/manifest.json). No v2 privacy evaluation
has run. Manifest SHA-256:
`bb284c1cc701eadf3e7b4dc463e8bf6f46cc6cd606436e033d8cbee3fbf43093`.

This is a separate dataset from the spent v1 set. V1 footage, manifest, policy,
results and caches remain untouched. V2 is benchmark-only, has no prepared audio,
and is never demo-ready. No third-party logo/brand clearance or demonstration
claim is made. The original downloads can contain audio; only silent derivatives
may enter the benchmark.

The selection was sealed at `2026-10-30T15:37:43.266363Z`, before any pixel decode,
using public Commons descriptions, license/revision records, dimensions and
durations. Its SHA-256 is
`8d70354743f64dcbfb5305c67c8a4b1ab4a98f12d456dc773e2b64178d81cb0e`.
The [selection](../fixtures/fresh-heldout-v2/selection.json) binds all three
source identities, excerpts and seeds. No sources may be substituted based on
frames, OCR, detectors or eventual scores.

| ID | Commons original / revision | Author | License | Seed |
| --- | --- | --- | --- | --- |
| `london-westminster` | [Walking in London](https://commons.wikimedia.org/wiki/File:Walking_in_LONDON_-_England_(UK)_-_Westminster_to_Piccadilly_Circus_(2019)_-_4K_60fps_(UHD).webm), [revision 1157657701](https://commons.wikimedia.org/w/index.php?oldid=1157657701) | [POPtravel](https://www.youtube.com/channel/UClODDXeUIz1-FaKyN8dsNrA), [original](https://www.youtube.com/watch?v=BgMKsDwIDgQ) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | 770453041 |
| `paris-walk` | [Paris walking travel tour](https://commons.wikimedia.org/wiki/File:Paris_,_France_-_A_Walking_Travel_Tour_-_YouTube.webm), [revision 1031020312](https://commons.wikimedia.org/w/index.php?oldid=1031020312) | [Le Monde en Vidéo](https://www.youtube.com/user/allairej1957), [original](https://www.youtube.com/watch?v=O4W4X_UBRkg) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | 953878931 |
| `liverpool-walk` | [Walking in Liverpool](https://commons.wikimedia.org/wiki/File:Walking_in_LIVERPOOL_-_UK_-_4K_60fps_(UHD).webm), [revision 1053656681](https://commons.wikimedia.org/w/index.php?oldid=1053656681) | [POPtravel](https://www.youtube.com/channel/UClODDXeUIz1-FaKyN8dsNrA), [original](https://www.youtube.com/watch?v=jKJ2zDSYns8) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | 2355994416 |

File-page API snapshots, including revision wikitext and license fields, are in
[commons/](../fixtures/fresh-heldout-v2/commons/); access date is **2026-10-30 UTC**.
All three originals are reported as 1920×1080. This is a statement about original
file dimensions, not native capture or absence of earlier upscaling. The Latin
script / European street match and walking motion are inferred from documented
locations and tour descriptions. Whether the fixed interval contains readable
signs or continuous camera motion is unverified. London and Liverpool share an
author; these are not three independent capture styles. Paris is documented as
a tour filmed over three days. Selection did not use actual scene contents.

[Nonreuse evidence](../fixtures/fresh-heldout-v2/nonreuse.json) names and hashes
528 physical corpus files (including repeated fixture copies across worktrees):
fixture manifests/evidence across standing worktrees, prior
candidate reports, the earlier metadata/search receipts and root manifests.
After URL decoding, replacing underscores with spaces and case folding, each
selected title, file-page URL, original URL and SHA-1 is absent throughout that
corpus. All four fields are pairwise distinct within v2. The unused Seattle
Alaskan Way Viaduct backup is explicitly excluded. This proves source identity
nonreuse against that enumerated corpus, not visual independence of scenes.

## Deterministic recipe

Every source uses exactly **2.000–7.000 seconds**, selected before pixels. Seeds
are big-endian uint32 values from the first four SHA-256 bytes of UTF-8
`fresh-heldout-v2:` followed by the stable clip ID. The natural derivative keeps
the established v1 encoding recipe: `h264_nvenc`, preset `p4`, bitrate `10M`,
`yuv420p`, scale/crop to 1280×720, `fps=30:start_time=0`, square pixels and a cap
of exactly 150 frames. Source audio, subtitles, data, metadata and chapters are
removed. MP4-generated structural metadata remains. No CPU codec substitutes
for the dataset's NVENC recipe.

Synthetic frames use the unchanged `bench.synthetic.overlay`, existing bundled
fonts and v1 optical-flow camera translation recipe. OpenCV operations are CPU
only, with one CV thread and two FFmpeg decoder threads; OpenCL is disabled.
Each synthetic truth frame records four exact strings, stable IDs, ink quads,
visibility and bounding boxes. Natural truth is 150 empty arrays of synthetic
truth; it is not natural-text OCR ground truth. No detector, OCR, judge cache,
privacy mask or quality score is produced by this preparer.

## Frozen locations and retention

The full canonical cache, including the original WebM downloads, is retained at
`/home/elan/.t3/worktrees/irl-shield/t3-8679bc10/fixtures/cache/fresh-heldout-v2/`.
That worktree remains locked through the one-shot evaluation and submission;
**do not unlock it or remove its cache**.

A durable copy of the derived MP4s, truth and preparation receipts is also at
`/home/elan/code/irl-shield/fixtures/cache/fresh-heldout-v2/`. This copy does not
replace the canonical originals. The conductor rehashed the twelve
manifest-pinned video/truth files after copying them and found no mismatches.

Transfer the frozen bytes intact. **Never re-encode these assets**, substitute
another excerpt, regenerate truth, or rebind the manifest to replacement hashes.
An empty checkout must receive the canonical files rather than run a new encode.

## Preparation and transfer

Use the existing pinned Python environment; no installs are needed. During initial preparation,
run CPU-only `download` then `plan` with
[prepare_heldout_v2.py](../fixtures/prepare_heldout_v2.py). Downloads are serial,
capped at 3 MiB/s and resume retained partials using exact HTTP ranges. The
preparer verifies original byte counts and Commons SHA-1, computes SHA-256 and
writes a new plan with exclusive creation. CPU work uses the canonical shared
lock, nice 10, native thread limits of two and `app-t3code-agents.slice`.

The commands below are a historical record of first-time preparation, not
instructions to repeat it. The frozen plan and manifest already exist. Retain
their bytes and transfer the canonical sealed cache into an empty checkout.

```bash
nice -n 10 env OMP_NUM_THREADS=2 OMP_THREAD_LIMIT=2 OPENBLAS_NUM_THREADS=2 \
  MKL_NUM_THREADS=2 scripts/host-lock shared python3 \
  fixtures/prepare_heldout_v2.py download
nice -n 10 env OMP_NUM_THREADS=2 OMP_THREAD_LIMIT=2 OPENBLAS_NUM_THREADS=2 \
  MKL_NUM_THREADS=2 scripts/host-lock shared python3 \
  fixtures/prepare_heldout_v2.py plan
```

After explicit `GPU_RELEASED`, root submitted one `prepare --clip` job per
source to the canonical EX queue, ahead of quality arms. The functional phone
test was still unfinished; it was not a GPU prerequisite. Exact Python
and FFmpeg argv are in the worker's `out/v2-prep/timed-jobs.json`. The preparer
validates the inherited canonical lock descriptor and queue attempt receipt,
without acquiring another flock. Inherited nice 10, agent slice, two native
threads and one CV thread keep the machine usable. The source and recipe code,
fonts, original/derived/truth bytes, metadata and queue receipt references are
bound in preparation receipts. Existing derived assets cannot be overwritten.

Once all three preparation jobs finished, CPU-only `freeze` assembled the
manifest with exclusive creation. `verify` rehashes originals and all derived/truth files,
checks the sealed selection and code identity and decodes every derivative to
verify 150 frame timestamps at `i/30`, zero origin, 1280×720 and no audio. The
frozen cache is gitignored under `fixtures/cache/fresh-heldout-v2/`. Transfer it
intact for later use; re-encoding on another GPU/FFmpeg build can change bytes.
Never rebind the frozen manifest to a new encoding.

Run `verify` from a dedicated checkout of **`d97ad2e`**, with a byte-for-byte
copy of the full frozen cache available there. It compares the preparation
receipts' code identity with the checkout's live shared source files; an arbitrary
later checkout is not the verification reference. The durable derived-only copy
is insufficient for this command because verification also hashes the originals.
Do not change or unlock the canonical originals worktree to create this checkout.

```bash
# From the dedicated d97ad2e checkout with the complete frozen cache:
nice -n 10 env OMP_NUM_THREADS=2 OMP_THREAD_LIMIT=2 OPENBLAS_NUM_THREADS=2 \
  MKL_NUM_THREADS=2 scripts/host-lock shared python3 \
  fixtures/prepare_heldout_v2.py verify
```

The manifest's `evaluation_marker` and `evaluation_reservation` are
**declarations, not enforced execution guards**. Main's current evaluator
hard-codes v1 and fails closed for v2. The v2 harness follow-up must add durable
tracked started-state, the `not_before_utc` check and final-policy binding before
any v2 evaluation. Until that follow-up lands, this reservation is an operational
rule, not a claim that the existing harness enforces one-shot execution.

Exactly **one** future evaluation is reserved for the final policy after the
**Sunday, November 1, 2026, 06:00 PT / 14:00 UTC** policy freeze. This preparation
does not authorize the coordinator to grade it, and it must not be used by
Saturday's v1 walk policy. Harness support and evaluation enforcement belong
to the quality coordinator. The manifest remains immutable `frozen-ungraded`;
any later evaluation state belongs in separate retained receipts.

## Retained verification

Root ran exactly one physical NVENC preparation per source under the canonical
EX queue. London had one pre-execution rejection before its single successful
execution. All three actual executions were deliberately forced/contended
functional preparation; they establish no performance qualification. The
worker's `out/v2-prep/root-completion.json` preserves the joined queue receipt.
The source, plan and invocation wrapper remained pinned throughout these jobs.

The worker ran a red/green selection-contract test and a CPU-only generated
technical fixture check. The latter accepted a 150-frame zero-origin silent
video and rejected 151 frames, nonzero origin and an audio stream. Its temporary
libx264 fixture is separate from the six NVENC dataset videos. Final `freeze`
and `verify` rehashed originals/derived/truth and checked every derived frame
timestamp. The asset audit records the six streams, source nonreuse, exact
synthetic truth counts (450 frames / 1,800 label records), and absence of judge,
mask, score or evaluation-marker files. Complete receipts and the invocation
ledger are retained in `out/v2-prep/`; no quality numbers were produced.
