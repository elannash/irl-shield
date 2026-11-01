# Fresh heldout v3 harness contract

This document describes source readiness, not an executed evaluation. No v3
source selection, dataset hashes, media, real start receipt or real reservation
marker is supplied by this change. V2 remains spent; its receipt, host marker,
cache and reservation are not a source for v3.

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
physical evaluation. Monday 09:00 PT live activity remains owner-only.

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
| `option_files` | Empty in this implementation; reserved contract for future resource consumers |
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

## Forthcoming local OCR and GGUF resources

The current baseline has no consuming local OCR/GGUF policy adapter. A selected
`local_ocr_model`, `gguf_model`, or nonempty `resources.option_files` therefore
refuses before reservation. Accepting arbitrary declarations while the renderer
ignores them would give a false readiness result.

A future consuming adapter must bind each selected option to a cache-relative
filename with SHA-256 and byte pins, include tokenizer/config/projector/dictionary
or other sidecars actually required by that consumer, derive its dependency set
from that same selection, and pass verified absolute bindings to the real loader.
It must reject missing/extra bindings and unsupported selections and extend the
family/judge registry when a new detector requires it. It must retain this receipt
ordering. A caller assertion or an optional unchecked file list is insufficient.
The empty field here reserves no model identity and authorizes no such adapter.

## Unexecuted validation and provisioning

`out/v3-harness-preflight-v1/` contains the source patch, source hashes/modes,
static hand-back, test plan and ten-call root validation packet. The worker ran
only source/metadata reads, edits, AST parsing and diff checks. It ran no tests,
project/SDK imports, media reads/decodes, model execution, native/GPU work, queue
calls, SSH, devices or Twitch calls.

The dedicated worker tree has no `.venv` or model cache. The conductor must provide
its real Python 3.11 environment and exactly the final selected payloads and
static caches in the actual run tree; pin actual distributions and FFmpeg binaries;
verify selected native providers, hardware readiness, output space and independent
Mac judge resources; and run the retained focused proofs plus full gate itself.
No resource pin or real v3 dataset is fabricated to fill that gap. No bench result,
privacy score or performance claim exists for this implementation yet.
