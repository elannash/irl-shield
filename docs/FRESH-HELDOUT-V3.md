# Fresh heldout v3 harness contract

The metadata-selected sources are sealed in
[`selection.json`](../fixtures/fresh-heldout-v3/selection.json), with attribution
and nonreuse evidence beside it. The CPU preparer produces a separate
frozen-ungraded dataset manifest after verifying the originals and all six
inputs. A source-selection seal or prepared dataset is not an evaluation.
V2 remains spent; its receipt, host marker, cache and reservation are not reused.

Original seal: `738b738`; re-seal commit: the commit adding `preparation-plan.json`; selection and all six inputs are unchanged.
`tools/check_v3_reseal.py` asserts equality to that seal; reservation remains not started, not before `2026-11-02T12:00Z`.

V3 accepts exactly three distinct source identities and all six natural and
synthetic pairs. Its dataset ID is `fresh-heldout-v3`, its frozen cache prefix is
`fixtures/cache/fresh-heldout-v3`, and its manifest marker path is
`fixtures/cache/fresh-heldout-v3/EVALUATION.started.json`. The immutable
reservation requires `maximum_evaluations: 1`, `evaluation_started: false`, and
`not_before_utc: "2026-11-02T12:00:00Z"`. The wall clock and the explicit final
policy commit's committer time must both reach that freeze. The final policy
commit remains authoritative after the receipt advances HEAD.

The conductor seals real source selection and the dataset before any new tuning
output, provisions the actual execution tree, and commits the final policy after
the freeze. This source change does not release those fences or authorize any
physical evaluation. Live activity requires separate owner authorization.

## Before consuming the attempt

The v3 start requires the exact committed source checkout, dataset/policy hashes,
existing source/family/area guards and the canonical host EX lease. The lease
covers the complete start and all six render calls. All-ref spent scans run before
and after lease acquisition; tracked results remain an additional spent guard.
Preflight Git status disables optional locks so it cannot refresh the index before
resource validation.

`--cache-root` relocates only frozen dataset assets and retains every frozen
relative path/hash. It still requires a separate `--state-directory`.
`--model-cache` is separately mandatory for v3: it binds existing selected model
payloads, not dataset media. It never downloads files and does not change frozen
policy options. V1 and v2 do not acquire this new resource contract.

The final policy contains a `resources` object with exactly these fields:

| Field | Contract |
| --- | --- |
| `schema_version` | Integer `1` |
| `model_manifest_sha256` | SHA-256 of committed `models/manifest.json` |
| `distributions` | Exact distribution names and installed versions required by the selected policy |
| `executables` | Exactly `ffmpeg` and `ffprobe`, each with positive `bytes` and lowercase `sha256` |
| `derived_models` | Exact selected static ONNX filenames, each with payload pins and `derivation`; empty when static models are unused |
| `minimum_free_bytes` | Positive output/state free-space threshold chosen with the final policy |

Model identities come from the committed model manifest, not caller-supplied
replacement weights. The accurate candidate and resolved fast candidate determine
which model payloads are required. Unselected manifest models are neither read nor
downloaded. Controls require no model payload. The validator checks file existence,
size, SHA-256 and cache containment, including symlink targets.

Base distribution pins are `numpy`, `opencv-python-headless` and `psutil`.
Selected PP-OCR models add `rapidocr`, `omegaconf`, `pyclipper`, `shapely` and
exactly one ONNX Runtime distribution. CUDA selects `onnxruntime-gpu`; otherwise
`onnxruntime` is required. Co-installed CPU/GPU distributions refuse. Static
models also require `onnx`. Selected modules must import successfully. Available native execution providers are checked
without constructing an inference session. FFmpeg's encoder list must include
the selected supported encoder. This checks compiled availability; hardware
initialization and successful rendering still need the conductor's physical
validation.

For static models the validator runs the renderer's shape preprocessing on
synthetic zero arrays using frozen clip dimensions and selected lane options.
It requires every corresponding pre-existing derived cache artifact and rejects
extra derivations. Each `derivation` holds the existing recipe name
`ppocr-static-io-and-shape-inference-v1`, source model SHA-256, tensor height/width,
and ONNX version. Its canonical sorted compact JSON SHA-256 determines
`det-static-<key>.onnx`. Derivation bytes are separately pinned. No derivation is
created during preflight. At rendering, the existing static-model implementation
also verifies its deterministic derived bytes.

Output/state paths must obey the existing ignored-placement and separation
checks. They must be separate from the model cache. Preflight writes and fsyncs
an anonymous temporary file in each existing destination ancestor, checks free
space, and leaves no receipt or reservation marker there. Read-only ancestors
refuse before spending, including when the process has elevated filesystem
access. Receipt and host-state destinations are checked as well.

## Receipt and first-render ordering

Only after the preceding checks succeed does the harness:

1. Exclusively create and fsync the host's v3 spent marker outside Git/scratch.
2. Exclusively write and commit `bench/results/fresh-heldout-v3-started.json` as
   the sole child change of the exact original policy commit, with hooks enabled.
3. Exclusively create the fsynced Git ref
   `refs/irl-shield/fresh-heldout-v3/<dataset-sha256>/started` using an all-zero
   expected old object ID. An existing ref is never overwritten.
4. Verify HEAD, policy parent, sole receipt diff, receipt contents, clean source
   state and ref target. Then create the local spent marker and output snapshots.
5. Recheck the committed receipt and ref before every render. The v3 bundle
   entry also requires that receipt and checks its dataset, policy and resource
   identity before copying/decoding media. Resource availability is rechecked.

The ref retains the receipt even when a detached HEAD moves or resets; linked
worktrees share it and the existing `rev-list --all` scan finds it. Failed commits
or ref creation permit no render. The host marker remains spent, including if
repository reachability is later lost. There is no alternate host-state path or
retry/unspend command.

The verified model-cache path reaches the actual ONNX session constructor. The
legacy lane factory filters out `cache_dir`, so the bundle scopes the ONNX module's
actual cache default during backend construction under the host lease and restores
it on exit. This also binds static derivation and CoreML compilation paths. The
bundle records the actual resource binding; the start receipt, evaluation state,
six-pair aggregation and grading preflight retain and compare it. Frozen policy
options and the original `policy_commit` are preserved.

## Receipt-commit readiness

Before the v3 host reservation, the harness checks author and committer
identities, requires commit signing to be disabled, and rejects executable
commit or reference-transaction hooks. It also checks Git lock files and
exercises write/fsync in the actual index, HEAD, object, ref and reflog ancestors.
It does not disable hooks or signing on the operator's behalf. Unsupported
configuration must be resolved before the final run. The frozen policy commit
remains the receipt's parent; readiness never substitutes a later HEAD.

These checks refuse known environmental failures before spending the attempt.
A failure or environmental change after reservation still fails closed; no
render is permitted without the committed, referenced start receipt.

## Grading readiness

V3 holds one host lease across readiness and all six grades. Before creating
`JUDGING.started.json` or changing evaluation state, it constructs the actual
three-reader owner and exercises Tesseract, Apple Vision and PP-OCR on synthetic
pixels without consulting the evidence cache. Missing resources or reader
failure leave grading unspent; initialized resources are closed on failure.
The validated owner is reused for all six bundles and closed afterward. The
three synthetic reader calls are readiness checks, not heldout grades.

On Darwin, `TMPDIR` must be set to the OS-derived `DARWIN_USER_TEMP_DIR` value.
This assertion prevents the previously diagnosed Tesseract temporary-file
failure. The harness checks it; it does not change process environment or OS
settings. Source, frozen input, family, area and six-pair checks still precede
heldout grading. A failure after actual judging begins retains the one-shot
marker and partial result.

## Provisioning and validation

Provide Python 3.11 and the exact selected dependencies, detector cache,
FFmpeg/FFprobe binaries, native providers and encoder described by the policy.
The offline renderer does not use MediaMTX. A native relay run must verify its
separate MediaMTX pin. Provision the independent Mac readers in the grading
checkout before launch; a default cache path is usable only if its actual
resources initialize and pass readiness.

Reproduce the synthetic harness and preparer regressions with the pinned
interpreter, serialized under the project's canonical queue lease:

```sh
PYTHONPATH=.:tests "$SHIELD_PYTHON" -m unittest -v \
  test_heldout_resources test_heldout_bench test_quality_bundle \
  test_prepare_heldout_v3 test_judge_cache
```

Run `scripts/check` for the complete gate. Synthetic tests and preparation
checks do not establish recall, privacy quality or native runtime performance.
The final score is the single independently judged evaluation after the
reservation opens. Future resource-consuming features must add their actual
loader/dependency bindings before a final policy selects them; an arbitrary file
list or ignored policy option is not evidence of readiness.
