# Fresh Q heldout preparation and one-shot evaluation

This dataset is frozen and **ungraded**. It contains the three preferred new
Commons sources, each with a natural and synthetic variant. It is separate
from the existing seven tune clips and old three heldouts. No detector, OCR
judge, masking evaluation or score selection was run on these new clips.
The assets are benchmark-only and never demo-ready.

Preparation fixes the 2.000–7.000s excerpt and seed before any image inspection.
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
natural text truth can only come from the later independent judges.

Selection used documented source scenes and technical validity only. No frames
were shown to a human, OCR engine or privacy detector. Actual text density,
camera motion suitability and natural readability remain unverified. No backup
was substituted. The first download script assigned two IDs by API page order;
the mapping was corrected by exact title, checked against the specified original
hashes, and all final derivatives were made afterward. A backup original fetched
by that mistake was removed and is outside the freeze.

## Reproduce preparation or transfer the freeze

The cache under `fixtures/cache/fresh-heldout/` is gitignored and remains live.
The conductor can read it directly with `--cache-root`; copying media into the
root checkout is unnecessary. Transfer it intact only if another host needs it. Source, output, truth and preparation receipts
are hash-bound. Re-encoding on another GPU/FFmpeg build may produce different
bytes: never update the frozen manifest to accept them. Transfer the frozen
cache for the final evaluation instead.

On Linux, with an empty destination cache and the existing public media downloads
authorized, repeat **one clip per root quality lease**:

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

## Conductor's final evaluation — not executed by this worker

First finish **all a8 tune judging and aggregation**. Only then integrate this
patch: changing `bench/quality_bundle.py` changes its recorded orchestrator SHA
and would invalidate in-progress a8 grades. Its default dataset remains the
same exact seven tune pairs / fourteen entries, with the same scoring code.
The explicit `dataset=` path adds the new three-source/six-pair contract.

Freeze the winning policy JSON `{ "candidate": ..., "options": ... }` and
commit the final executing source. Record that commit and the policy file's
SHA-256. Require a clean source checkout for the handoff; the command checks
that the supplied policy commit equals checkout HEAD and binds the actual
executed source/helper bytes separately. No family overrides are supported;
finite area ceiling in [0,1] and its explicit basis are mandatory.

The command has two physical stages because the policy runs on Linux CUDA and
Apple Vision judging runs on Mac. They are one evaluation with one frozen
identity. `render` spends a dataset-local `EVALUATION.started.json` using
`O_EXCL` **before** any detector work. A different output directory cannot reset
it when the same retained state directory is used. With `--cache-root`, a
separate `--state-directory` is required, so no marker is written to the read-only
asset cache. Keep that state directory fixed for this dataset. `grade` spends the transferred corpus's `JUDGING.started.json` before OCR.
Failure after either start is reported as `partial-failed`; do not delete the
marker or repeat the physical attempt. Preflight failures do not spend it.
An interrupt/power loss can leave a `rendering`/`judging` state and spent marker;
that is incomplete evidence, never permission to rerun or claim a pass.
These are accidental-repeat guards on the retained cache/corpus, not a global
service preventing an operator from deliberately copying an unspent cache.

Use the existing root GPU environment, native thread caps of 2, private CUDA
libraries, an owned writable CUDA cache, nice10 and the agent slice. The runner
itself takes the root quality EX and canonical perf SH leases **per clip**.
Do not put the whole command inside `q-run exec` or `host-lock`: that would nest
the same exclusive quality lease. Queued timed jobs take precedence.
For example, from the final Linux checkout with its root GPU environment set:

```bash
# Freeze these values from the reviewed policy and input snapshot beforehand.
# DATASET_SHA256 is also recorded in out/fresh-heldout/handback.json.
q_root=/home/elan/code/irl-shield
q_python="$q_root/.tmp/linux-probe/.venv/bin/python"
export OMP_NUM_THREADS=2 OMP_THREAD_LIMIT=2 OPENBLAS_NUM_THREADS=2
export VECLIB_MAXIMUM_THREADS=2 CUDA_CACHE_PATH="$PWD/.tmp/fresh-heldout/cuda-cache"
mkdir -p "$CUDA_CACHE_PATH"
q_libraries=()
for directory in "$q_root/.tmp/linux-probe/.venv/lib/python3.11/site-packages/nvidia"/*/lib; do
  [[ -d "$directory" ]] && q_libraries+=("$directory")
done
export LD_LIBRARY_PATH="$(IFS=:; printf '%s' "${q_libraries[*]}")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
systemd-run --user --scope --slice=app-t3code-agents.slice nice -n 10 \
  "$q_python" "$q_root/scripts/bounded.py" 1800 \
  "$q_python" -m bench.heldout_bench --root "$PWD" --lock-root "$q_root" render \
  --dataset fixtures/fresh-heldout/manifest.json --dataset-sha256 "$DATASET_SHA256" \
  --cache-root /home/elan/.t3/worktrees/irl-shield/t3-dbc6f7a0/fixtures/cache/fresh-heldout \
  --state-directory "$q_root/.tmp/q/fresh-heldout-once-state" \
  --policy "$POLICY_FILE" --policy-sha256 "$POLICY_SHA256" \
  --policy-commit "$POLICY_COMMIT" --directory out/q-fresh-heldout-once
```

Transfer the **whole** `out/q-fresh-heldout-once` directory unchanged and the same
executing sources to the Mac. The Mac needs the existing Tesseract, Vision and
PP recognition installations. It does not need the original Linux cache for
judging. From that Mac checkout, set `q_root` to its canonical serialization
checkout and use its existing Python:

```bash
nice -n 10 "$q_root/.venv/bin/python" "$q_root/scripts/bounded.py" 1800 \
  "$q_root/.venv/bin/python" -m bench.heldout_bench \
  --root "$PWD" --lock-root "$q_root" grade \
  --directory out/q-fresh-heldout-once --cache .tmp/fresh-heldout/judge-cache
```

No command here grants an additional heldout attempt. The owner already
reserved the final one-shot evaluation for the conductor after policy freeze.
No approval prompt or token is added.

Each clip uses the existing `render_offline`, `_score_saved` and
`build_scorecard` paths. Natural truth and synthetic input controls exclude all
registry-declared detector families; **all output judges** count credible leaks.
Source identity is checked before and after OCR. The aggregate requires all six
unique pairs, identical policy/options, frozen inputs, source/helper identity,
unchanged local sealed media/truth/masks, and unchanged grade/evidence hashes.
The same real-video, per-clip/aggregate protected-frame and masked-area guards
apply. A subset or slate cannot pass. The output remains `offline_quality`,
`real_time_verified=false`, `gate_1.pass=false`, even if content guards pass.
No offline output can earn a performance pass.

## Verification scope

`tests/test_heldout_bench.py` uses tiny generated clips and the existing fake
pixel detector/judges, never heldout pixels. It exercises frozen pair/hash/path
validation, actual sealed relocation after removing original input files,
missing third pair, mixed policy, preflight media changes, one-shot rendering
after success/failure, all-six one-shot judging after relocation, and a read-only
cache override with unchanged asset hashes and a separate writable marker.
The existing suite owns independent truth/control versus all-output-judge
semantics, copied source/truth races, source checks around OCR, real-video and
area/protected guards; those tests are reused without duplicating TestCase
discovery. Physical guard mutations and the Linux gate receipts are recorded
in `out/fresh-heldout/handback.json`. Failed attempts and corrections, including
the initial Python environment and stale-bytecode verification failures, remain
in `out/fresh-heldout/ledger.json`; they are not passing verification receipts.

This worker did not run Mac OCR, heldout model inference, native performance,
Twitch, deployment or any external write. The Linux bench+M2 gate is not the
project's full Mac/Twitch gate; the known separate M3 unified-discovery gap is
owned by integration. The conductor still owns independent review, applying
and committing the patch, final policy freeze and the actual one-shot run.
