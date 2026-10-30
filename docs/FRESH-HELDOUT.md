# Fresh Q heldout preparation and one-shot evaluation

This dataset is **spent**: it was rendered once on Linux and OCR-graded once
on the Mac. The [one-shot result](Q-FRESH-HELDOUT-RESULT.md) and
[tracked scorecard](../bench/results/q-fresh-heldout-once.json) record that
Gate 1 did not pass. No policy was tuned from the result. The three Commons
sources each have a natural and synthetic variant, separate from the existing
seven tune clips and old three heldouts. The assets remain benchmark-only and
are never demo-ready. No further heldout render or grade is permitted.

The manifest retains its original `frozen-ungraded` status to preserve its
frozen bytes and identity; that field describes the preparation snapshot,
not the dataset's current evaluation status. `start()` checks tracked
`bench/results/*.json` for a matching `heldout_freeze.dataset_sha256` before
creating any marker or output, so removing scratch does not reset spent state.

Preparation fixed the 2.000–7.000 s excerpt and seed before any image inspection.
Seeds are the big-endian integer of the first four SHA-256 bytes of
`fresh-heldout-v1:` followed by the clip ID:

| Clip | Seed | License |
| --- | --- | --- |
| `zurich-spiegelgasse` | 863287663 | CC0 1.0 |
| `chicago-wells` | 3291828478 | CC BY 3.0 |
| `manchester-portland` | 1582902036 | CC BY 3.0 |

[Attribution](../fixtures/fresh-heldout/ATTRIBUTION.md) records authors, original
pages, revisions, licenses and modifications. The frozen
[manifest](../fixtures/fresh-heldout/manifest.json) binds original byte counts,
SHA-1/SHA-256, metadata snapshots, derived media, truth, seeds and recipes.
All paths used as inputs are checkout-relative. Copied bundle inputs are
verified locally after relocation; Linux absolute paths in preparation command
receipts are historical provenance, never paths used to grade on Mac.

Every derived clip is exactly 150 zero-origin CFR frames at 1280×720 and 30fps,
with no audio. The natural encode uses the existing fixture preparer's NVENC
p4/10M/yuv420p scale/crop recipe, with explicit `fps=30:start_time=0` and a
150-frame cap. Manifest SHA-256:
`46a4461ca50ac54a4cac564ad81e1bba5c2d990b0cb9976eb473a82e5fcc3cad`.
The start normalization is necessary because Manchester's
unadjusted recipe emitted 149 frames starting at 0.033008s; that attempt was
rejected before freeze. All three clips use the same final recipe. All source
metadata, chapters and audio are discarded; MP4-generated structural fields
remain. The synthetic variant uses `bench.synthetic.overlay`, existing fonts
and label styles/positions, and the same optical-flow camera tracking recipe
as `bench.run.variant`. This is fixture generation, without privacy detection.
Its truth records every frame's exact strings, ink quads, visibility, stable IDs
and boxes. The natural variant has 150 empty arrays of **synthetic** truth;
natural text truth in the completed evaluation came from independent judges.

Selection used documented source scenes and technical validity only. Before
freeze, no frames were shown to a human, OCR engine or privacy detector. The
completed evaluation now records OCR-observed text and readability; real-world
privacy coverage and camera motion suitability remain unverified. No backup
was substituted. The first download script assigned two IDs by API page order;
the mapping was corrected by exact title, checked against the specified original
hashes, and all final derivatives were made afterward. A backup original fetched
by that mistake was removed and is outside the freeze.

## Historical preparation and frozen cache

The cache under `fixtures/cache/fresh-heldout/` is gitignored and remains live.
The conductor can read it directly with `--cache-root`; copying media into the
root checkout is unnecessary. Transfer it intact only if another host needs it. Source, output, truth and preparation receipts
are hash-bound. Re-encoding on another GPU/FFmpeg build may produce different
bytes: never update the frozen manifest to accept them. Transfer the frozen
cache for retained evidence instead. The one-shot evaluation is already spent.

During preparation on Linux, the worker used an empty destination cache and
existing public media downloads, **one clip per root quality lease**. This is
a historical command record, not an instruction to recreate the spent set:

```bash
q_root=/home/elan/code/irl-shield
q_python="$q_root/.tmp/linux-probe/.venv/bin/python"
for clip in zurich-spiegelgasse chicago-wells manchester-portland; do
  "$q_root/scripts/q-run" "$PWD" exec -- "$q_python" \
    fixtures/heldout_prepare.py prepare \
    --plan fixtures/fresh-heldout/manifest.json --clip "$clip"
done
```

The preparer refuses existing derived files, verifies downloaded originals and
fails if regenerated inputs differ from frozen hashes. The manifest preserves
Commons metadata so reproduction does not depend on mutable page text. During
initial preparation only, the separate `freeze --plan PLAN --output NEW_FILE`
action assembles already verified receipts, using exclusive creation. It runs
no detectors or judges. No new packages or models were installed.

## Completed one-shot evaluation — historical record

Tune judging and aggregation finished before the evaluator was integrated.
The default tune dataset remained the same seven pairs / fourteen entries;
the explicit `dataset=` path selected the three-source/six-pair frozen set.
No guard-valid tune winner was found, so the unchanged B6 diagnostic fallback
was frozen in [q-final-policy.json](../bench/q-final-policy.json).

The executed source was `26c8db18624731eaf92168e69aa97ddad31abd17`.
The policy SHA-256 was
`dcbc96c88b0a3c1545a5a04c668446eee1afeb730e901179ffc78063cb91ad5f`;
the dataset SHA-256 was the unchanged `46a4461c…` value above. The command
checked the supplied policy commit against checkout HEAD and bound actual
source/helper bytes separately. No family override was used. The finite area
ceiling and its explicit basis were part of the frozen policy.

The two physical stages formed one evaluation. Linux ran the
`bench.heldout_bench render` entry point with a read-only cache override at
`/home/elan/.t3/worktrees/irl-shield/t3-dbc6f7a0/fixtures/cache/fresh-heldout`
and writable state at `.tmp/q/fresh-heldout-once-state/`. It spent the
`46a4461ca50ac54a4cac564ad81e1bba5c2d990b0cb9976eb473a82e5fcc3cad.started.json`
marker before rendering into `out/q-fresh-heldout-once/`. The root launch
script is retained at `.tmp/q/render-heldout-once.sh`; terminal output is in
`fresh-heldout-render.log`. The existing GPU environment, private CUDA
libraries, two native threads, owned CUDA cache, nice 10 and agent slice were
used. The runner took quality EX and canonical perf SH leases per clip.

The whole sealed corpus and executing sources were transferred to the Mac.
The `bench.heldout_bench grade` entry point used the existing Tesseract,
Vision and PP recognition installations and `.tmp/fresh-heldout/judge-cache`.
It spent the corpus's `JUDGING.started.json` before OCR. The grade log is
retained at `fresh-heldout-grade.log`; `evaluation.json` finished as `complete`.
Both physical stages are spent. Neither marker may be deleted to retry a stage.
A different output directory or cleaned scratch does not create another
attempt: the tracked result now also makes `start()` refuse this dataset.

`O_EXCL` markers protect in-progress attempts, including a kill before the
first clip's state rewrite. Failure after a stage starts is incomplete evidence,
not permission to repeat it. Preflight failures create no marker. The tracked
scorecard preserves completed spent state across scratch cleanup and checkouts
that contain that result; this is not a global service against deliberate
removal of the tracked record.

Each clip used the existing `render_offline`, `_score_saved` and
`build_scorecard` paths. Natural truth and synthetic input controls excluded
registry-declared detector families; all output judges counted credible leaks.
Source identity was checked before and after OCR. Aggregation required all six
unique pairs, identical policy/options, frozen inputs, source/helper identity,
unchanged local sealed media/truth/masks, and unchanged grade/evidence hashes.
The existing real-video, per-clip/aggregate protected-frame and masked-area
guards applied. The result remains `offline_quality`,
`real_time_verified=false`, `gate_1.pass=false`. It establishes no performance
pass. The [result record](Q-FRESH-HELDOUT-RESULT.md) contains the verdict and
links to the complete scorecard and proof.

## Verification scope

`tests/test_heldout_bench.py` uses tiny generated clips and the existing fake
pixel detector/judges, never heldout pixels. It exercises frozen pair/hash/path
validation, actual sealed relocation after removing original input files,
missing third pair, policy/dataset/source preflights before OCR, preflight media
changes, tracked spent results without scratch state, one-shot rendering after
success/failure, and all-six one-shot judging after relocation. A kill-state
regression restores the exact pre-grade state bytes and requires the exclusive
judging marker to reject a retry without another grade call. A read-only
cache override test checks unchanged asset hashes and a separate writable marker.
The existing suite owns independent truth/control versus all-output-judge
semantics, copied source/truth races, source checks around OCR, real-video and
area/protected guards; those tests are reused without duplicating TestCase
discovery. Physical guard mutations and the Linux gate receipts are recorded
in `out/pr6-r1/handback.json` for the review fixes; original preparation receipts
remain in `out/fresh-heldout/handback.json`. Failed attempts and corrections, including
the initial Python environment and stale-bytecode verification failures, remain
in `out/fresh-heldout/ledger.json`; they are not passing verification receipts.

The PR6 round-1 repair uses only generated synthetic media. It does not rerun
Mac OCR, heldout inference, native performance, Twitch, deployment or external
writes. Its Linux receipt is the **b7f48bb gate minus Swift build (NOT RUN BY
DESIGN on Linux)**, not the unified merge gate or a Mac/Twitch qualification.
The conductor owns the unified gate after merging this repair in scratch.
