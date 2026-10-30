# First Q integration commit: P2 fixes

Implementation is integrated and uncommitted on `elannash/q-integration`, based
on merged main `631dc5b9bf7cb90c84f0d4aebf430fdcf24eb89c`. No Q scorecard has been
accepted. Opus owns commit, PR, review and merge. The independent Ultra test
review is pending; its findings will be resolved before calling this hand-back
fully reviewed.

| Finding | Result | Evidence |
| --- | --- | --- |
| Family override could pool truth silently | Any options family override throws before media/model work. Unknown families throw; explicit registered no-detector controls retain legitimate empty declarations. Candidate swapping derives current registry families. | docs/P2-FAMILIES.md and tests/test_p2_families.py |
| One-independent-judge gates untested | Actual mixed-policy cases cover all constructors. Four builders have acceptance mutations; the serial reference constructor has explicit insufficient-truth reporting coverage and remains permanently ineligible. | docs/P2-GATES.md, tests/test_judge_gates.py, tests/test_legacy_judge_gate.py |
| Fast default had three copies | `resolve_fast_candidate` drives metadata, offline runtime and clocked runtime. A changed declaration is observed through actual factory calls in both paths. | tests/test_p2_families.py, runtime-drift mutation receipts |
| Cache omitted OpenCV and English data | Schema3 includes installed OpenCV distribution versions and the configured Tesseract executable's active `eng.traineddata` canonical path and actual SHA256. Historical entries remain untouched. | docs/P2-CACHE.md, tests/test_judge_cache.py |
| Compile gate entered ignored venvs | `compileall -x '/\.venv'` excludes the Python3.14 NumPy inside the ignored model venv when checking with Python3.11. | scripts/check, .tmp/q/compile-venv-red.log and green log |

Primary scoring remains independent natural truth and synthetic input controls,
with **all judges** eligible to find output leaks. There are no detector-policy,
threshold, truth, label or mask changes in these P2 fixes.

## Integration and verification

The conductor verified and applied the three Codex patches after a file-copy
command hit a false-positive worktree-removal hook. No alternate-copy retry or
hook change was made. Root verified the applied source identities, completed
the serial constructor extraction and mixed-policy test, and ran both full gates.
The hook instance is resolved; the hook itself is an owner-only boundary.

Native Mac discovery passed without OCR: Tesseract5.5.4 reports the English
file under `/opt/homebrew/Cellar/tesseract/5.5.4/share/tessdata/eng.traineddata`,
SHA256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.
The identity records opencv-python-headless4.11.0.86 and macOS27.0.1. Full receipt:
`.tmp/q/native-mac-cache3-identity.json`.

Final full gates both exited0:

- Linux:126 main tests with one expected platform skip, three relay tests,
  and Python source compilation with the venv exclusion.
- Mac `scripts/check`:126 main tests with one expected platform skip, three
  relay tests, compilation and optimized Swift bridge build.

Logs: `.tmp/q/integrated-{linux,mac}-full-gate-final.log`. The complete working
tree includes one experimental quality-bundle unit test; the experimental helper,
its test/script/doc are separate from the requested first P2 commit. The P2-only
commit therefore has one fewer test, with identical P2 production/test sources.
The conductor runs its gate before committing/PR review as usual.

The initial integrated Linux run failed an existing timing-dependent queue
fixture. Its synthetic busy flag lasted150ms and could vanish before sampling.
The fixture now holds it until the synthetic observer acknowledges it. A
controlled300ms observer delay reproduces the old `completed` versus
`exhausted-contended` failure; the acknowledged fixture passes under the same
fault. This changes only the fixture, not production queue behavior. Its
17-test affected suite and both final full gates pass. Receipt:
`.tmp/q/queue-fixture-delay-proof.json`.

The legacy gate extraction retains every original expression. A physical
mutation forces its independent-judge report true; the mixed-policy test fails
with the named single-truth-judge assertion. Restoring exact source passes.
Receipt: `.tmp/q/legacy-gate-mutation.json`. Cache and shared-default mutations,
their actual red assertions, restored source hashes and child gate logs remain
linked from the three P2 lane documents. `bench/results/q-p2-proof.json` records
final source/log hashes, both full gates and native Mac identity.

No installs, downloads, network publishing, credentials or global configuration
changes were required. All root verification commands have exited. The old
schema2 Mac re-judge22977 stopped before OCR and is not used.

## Commit and continuation

Include the P2 source/test/doc paths in the proof manifest, this document and
`bench/results/q-p2-proof.json` in the first Q commit. Keep experimental
`bench/quality_bundle.py`, `scripts/q-run`, `tests/test_quality_bundle.py` and
`docs/Q-HARNESS.md` for a separate reviewed change. Nothing is staged.

After the first fixed commit and review, advance Q3's worktree without losing
its owned changes, freeze the common CUDA/NVENC offline baseline, and run fresh
Mac judging with schema3. Q1 and Q2 returned diagnostic rejections with no
production change or fresh corpus metrics. Q3's B12 trial remains held. The
old unjudged CUDA pilot is explicitly superseded; it supplies no Q result.

The executed-only queue retry cap is a separate requested change. Its worker
must preserve historical pre-exec records and never restart the live runner
mid-job. No production queue change is included here. Existing timed jobs,
lock paths and contamination thresholds remain unchanged. Lock security and
PerlLease replacement stay deferred until the overnight runners have stopped.
