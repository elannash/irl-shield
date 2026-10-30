# P2 family validation and lane provenance handback

Implementation is complete and uncommitted on `elannash/q-p2-families`, based on
`631dc5b9bf7cb90c84f0d4aebf430fdcf24eb89c`. Initial worktree status was clean;
its tree `16d6dc319ce914d898863cb02c9c55c2799a203e` equals the tree of
`0648e0f64d599b223d101f6643ed7d75a36331e3`. The app-assigned branch was renamed
in place. No stage, commit, push, PR, merge, worktree creation or removal occurred.
Opus retains review and commit ownership.

## Changes and integration contract

- `resolve_fast_candidate` in `bench/independence.py` is the single resolver
  used by policy metadata, offline backend construction and clocked backend
  construction. Both runtime copies of the name-based default heuristic are gone.
  Registry defaults are unchanged.
- The resolver rejects **any** `options['detector_families']` key, even an empty,
  unknown, misspelled, stale-known or currently matching list. Consequently
  `policy_metadata`, `annotate_card`, `_make_backends` and the clocked setup all
  reject overrides. `run_file` resolves policy before output-path checks,
  probing, model loading, encoding or judging and uses that metadata for scoring.
- The root helper's preflight call to `policy_metadata(candidate, options)` inherits
  the same rejection before expensive work. A path that supplies detector backends
  directly to `render_offline` still needs that preflight: rendering itself has no
  candidate argument and does not establish provenance. No test-only option or
  export was added.
- `independent_readings` and `judging_scope` reject unregistered family names,
  including when there are no input frames. Registered `unmasked` and `slate`
  policies keep their legitimate empty family lists. A model candidate or model
  lane with an empty declaration raises. Low-level scoring still requires an
  explicit `detector_families` keyword; an explicit `[]` remains the no-detector
  control context, with no new default.
- `bench/run.py` no longer persists derived families in options. `score` now takes
  a candidate name in place of its old slate boolean, derives registry policy
  before decoding, and derives slate handling from that candidate. Its sole
  production caller migrated in the same change. Existing stored options that
  contain the removed family field now fail explicitly; they are never silently
  trusted or repaired.
- The encoded-pixel regression uses registered `unmasked` and `ppocr-v6-small`
  paths with synthetic detector/judge adapters. The PP path excludes PP-only input
  text (primary natural total 2, pooled diagnostic total 3) while a PP-only output
  reading still leaks an independent target on all four frames. Its exact raster
  pixel and SHA-256 assertions remain. The same source is rescored as a swapped
  PP candidate through `bench.run.score` with no family field in options.

No detector thresholds, labels, guard thresholds, scoring algorithms or output
judge filtering changed. Primary natural truth and synthetic input controls
remain independent; all credible output judges still count as leaks. No new
library, model, license obligation or asset was introduced. Generated synthetic
media is benchmark-only, silent, and removed by temporary-directory cleanup.

## Source reproduction and test design

The supplied review JSON is copied to
[review.json](../out/p2-families/review.json). Owned findings were reproduced
against base source before fixes: offline override selection at line 355,
permissive family handling in `independence.py:49–52` and `:66–74`, and the two
runtime default expressions at `offline_quality.py:201` and
`clocked_pipeline.py:755–756`. The expanded migration inspected `run.py:78–106`,
`:145` and `:166`. Exact numbered base excerpts are in
[finding-source-lines.txt](../out/p2-families/finding-source-lines.txt).

Tests observe existing interfaces: actual `run_file` and encoded pixels for early
validation and scoring, direct family validators for unregistered names, metadata
and annotation for central rejection, and actual calls to the detector factory
from both runtime constructors. The latter replaces the old literal default pin:
changing the declared Vision default to Paddle must both produce mixed-family
metadata with Tesseract-only truth and select Paddle at both factories. The
clocked test stops after factory selection and cleanup, before starting workers.
It proves constructor wiring, not throughput or model execution. System media and
model factory seams are supplied; no new test-only production seam exists.

## Red/green and mutation evidence

All receipts below are in `out/p2-families/`, with original scratch retained at
`/tmp/agents/irl-shield/p2-families/`. The [invocation ledger](../out/p2-families/invocations.txt)
contains 21 attempted test invocations of the 25 allowed, including the initial
scope-bus setup failure. Runs used nice 10, `app-t3code-agents.slice`, at most two
native workers and OpenCV one thread. Scope-bus environment variables were supplied
locally after the first failed launch. No global configuration changed.

| Slice | Red receipt | Green receipt |
| --- | --- | --- |
| Override rejection and unregistered direct families | `02-family-red.log`: 2 tests, 7 behavioral failures | `03-family-green.log`: 12 tests pass |
| Empty model declaration versus explicit controls | `04-empty-model-red.log`: model reaches media instead of rejecting; controls pass | `05-empty-model-green.log`: 14 tests pass |
| Changed declared default versus both runtime factories | `06-runtime-default-red.log`: both factories choose Vision instead of Paddle | `07-runtime-default-green.log`: 35 tests pass |
| Central metadata/annotation rejection and run.py migration | `14-central-and-score-red.log`: 6 rejection failures and old score's missing-field KeyError | `15-central-and-score-green.log`: 36 tests pass |
| Original source reintroduced on final tests | `16-final-family-mutation-red.log`: 5 tests, 15 behavioral failures and old score's missing-field KeyError | `17-final-family-restored-green.log`: 36 tests pass |
| Both duplicated runtime defaults reintroduced | `18-final-runtime-drift-mutation-red.log`: offline and clocked factory-name mismatches | `19-final-runtime-restored-green.log`: runtime test passes |

The final family mutation restores exact base bytes for `independence.py`,
`offline_quality.py` and `run.py`, then restores final source byte-for-byte.
[Its receipt](../out/p2-families/final-family-mutation.json) records the matching
base hashes, final hashes and restored hashes; the actual patch is
[final-family-mutation.diff](../out/p2-families/final-family-mutation.diff).
The drift mutation asserts each resolver replacement matches exactly once,
records a changed hash, and restores final bytes in `finally`.
[Its receipt](../out/p2-families/final-runtime-drift-mutation.json),
[diff](../out/p2-families/final-runtime-drift-mutation.diff), and
[runnable script](../out/p2-families/mutate-runtime.py) capture the proof.
Failures were the intended behavioral mismatches, not import or syntax errors.

The exact focused invocation after original-source restoration was:

```sh
/tmp/agents/irl-shield/p2-families/test-run 17-final-family-restored-green -v \
  test_offline_quality test_judge_independence test_p2_families test_clocked_pipeline
```

## Final Linux functional gate

The single final command was:

```sh
/tmp/agents/irl-shield/p2-families/final-full-gate \
  > /tmp/agents/irl-shield/p2-families/final-full-linux-functional-gate.log 2>&1
```

It exited 0 and sequentially ran:

1. All main tests in the existing `models/.venv311` CPU environment:
   **111 tests, one expected VideoToolbox/macOS platform skip**, no failures.
2. All relay tests in the existing `.tmp/m2/linux-venv` environment:
   **3 tests pass**, using in-memory synthetic NUT media, no sockets.
3. Python compilation of `bench`, `fixtures`, `models`, `shield` and `relay`:
   **exit 0**, with bytecode directed to owned scratch.

[Full gate log](../out/p2-families/final-full-linux-functional-gate.log),
[main-suite log](../out/p2-families/20-linux-main-suite.log),
[relay log](../out/p2-families/21-linux-relay-suite.log), and
[gate script](../out/p2-families/final-full-gate.py) retain exact commands and output.
No test was excluded to obtain this pass. `git diff --check` passes.

An earlier full attempt before the added `run.py` scope used the smaller probe
venv and failed: missing `pytesseract` prevented cache-test import, and one queue
contention assertion observed a nonzero child result. Its
[log](../out/p2-families/13-linux-main-suite.log) is retained. No queue code was
changed. The final all-suite run used the already installed environment documented
by prior Linux receipts and passed the queue test as well. No dependency install
or OCR/model execution occurred.

## Frozen source identity and remaining work

These SHA-256 hashes were frozen after the final gate; source and test files are
untouched afterward. The [source patch](../out/p2-families/final-source.patch)
includes tracked changes and the new untracked runtime regression. This document
and `out/p2-families/handback.json` are handback artifacts, not source code.

| Path | SHA-256 |
| --- | --- |
| `bench/independence.py` | `1b37989cf8c034717c927630728a17866edfcd8de5b1978ed20373408824d90c` |
| `bench/offline_quality.py` | `28a6a4281603c10838acb1fd028937ccc2cc7e84fabd871408d62f41499ea0a0` |
| `bench/clocked_pipeline.py` | `178aa49703d544b647d6198b16f1d0f714b5c253f34c1750205fdedd51893455` |
| `bench/run.py` | `ac566876db267b1275958a7fe537d21a6e42e0104c3194d0a3bbb3afd63331fa` |
| `tests/test_judge_independence.py` | `14de990a34473206bb7b6213eadb4a907d8c6ae2279eef37b49a7eb0cf587437` |
| `tests/test_offline_quality.py` | `7c720886f5ab469e2576ba8cb192f1ef2bd04d952ed696a0375579d39419622e` |
| `tests/test_p2_families.py` | `aaf4fb850dca997388cdbfd2248a82709a2cf7efc034c8fcc12d8bbbdc1f0633` |

Skills applied: codebase-design (one shared resolver), tdd and test-review gate
(red before green at existing seams), diagnosing-bugs source/hypothesis checks
(source reproduction before repair), receipt-audit (read all claimed logs and
restoration receipts), and research measurement rules (state exact suite scope,
platform skip and proof limits).

The owned implementation has no unfinished item. The parent still owns Mac full
CI/Swift and milestone benchmark validation, shared `scripts/check` decisions,
quality_bundle/q-run integration, Q1–Q3 numbers, and Opus review/commit. No Mac/GPU,
model download, OCR run, Twitch/network action, secret access, account creation,
publishing, or out-of-scope code edit was performed. The `tests/test_p2_families.py`
and `docs/P2-FAMILIES.md` additions remain untracked for the conductor; all existing
changed paths are tracked. All work is unstaged and uncommitted.
