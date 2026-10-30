# Q2 lane B recall ledger

2026-10-30. **PASS CPU/config readiness, ISSUES GPU timing seam, HELD execution.**
Base/HEAD `65891cb0b515bc0c34ec4ded89aa6a3228992cc2`.
Assigned branch preserved: `t3/q2-recall-detector-arms`.
Worktree `/home/elan/.t3/worktrees/irl-shield/t3-bccad190`, initially clean.
Locked: `Q2 recall lane code and synthetic receipts pending coordinator apply`.
No stage, commit, push, PR, checkout, worktree creation/removal or delegation.
Codex Sol XHIGH priority confirmed by thread-config read; no configuration write.

Task link:
<t3-thread://v2/a3857748-9579-4ce2-b37e-5d3cd3faad44/thread:delegated-task:command%3Amcp%3A4604c41b-99c6-432d-bed9-120571e9de69%3Adelegate-task%3Ad0d04b89-1576-4be2-8bcd-832f9ea26cab>

Read codebase-design, tdd, test-review gate, diagnosing-bugs Source/hypothesis,
research Measurements/metered calls, receipt-audit. No GLOSSARY/ADR path was
found; read `docs/ARCHITECTURE.md`. Read actual detector, static derivation,
registry, pipeline, quality harness, cache identity, CLI and adjacent tests.
Historical inputs/policies/plan and actual giant audit were read as metadata
only; no scene decoding, detection, OCR or historical regrading. Retrieval
receipts are separate in `out/q2-recall/retrievals.json`. Initial lock command
omitted its required path and returned usage; corrected exact-path command
locked only the assigned worktree.

## Changes and test rationale

Five one-knob opt-in JSON arms plus exact baseline copy; metadata-only command
preparer; CPU readiness tests; unexecuted own-mirror sync script. Shared source
is unchanged. `out/q2-recall/source-identity.json` records exact source hashes,
including all schema-3 judge-source contributors equal to base, and current
offline fingerprint `fa992bd3cfe8fff022eaa131bcb0090cdc64c9440665ba9dfdf44725d509c283`.
This is not the historical giant-audit pipeline fingerprint. Root needs a new
paired baseline. Actual Mac runtime cache-signature equality is **unverified**.

The new preparation-interface checks catch accidentally combined arms, silently
changed baseline bytes and substituted tune inputs before emitting commands.
No existing test owns these new opt-in inputs. They use temporary synthetic
metadata, no export/reset hook, and no mock. Each guard was physically removed,
the targeted assertion failed `ValueError not raised`, the pristine bytes were
restored, and green was rerun. These are mutation-proven guards, not a claim that
this lane reproduced or fixed a previously reported detector defect. Diffs are
saved as `out/q2-recall/{combined,inputs,baseline}-mutation.diff`.

The public detector preprocessor check uses synthetic zero arrays, confirming
accurate tensors `1x3x544x960` -> `1x3x704x1280`, fast unchanged `1x3x352x640`.
It catches a resolution arm that has no effect on the actual preprocessor;
it misses model runtime compatibility and accuracy, explicitly unverified here.
Clocked argv check catches inherited CLI defaults (`after=18`, fast=30 Hz,
phase minimum=.5) replacing explicit frozen options. It misses runtime timing.

## Invocation ledger (10 / 20 used, 10 remaining)

Every test/preparation/validation attempt counts, including expected reds and
the failed validation launch. Reads, hashes and packaging artifact writes are
retrieval/administration, not benchmark runs. No GPU, ORT session, NVENC, video,
OCR, quality, profile, queue submission or Mac invocation occurred.

Common exact command prefix for CPU invocations 1-9:

```bash
env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
OPENCV_FOR_THREADS_NUM=1 PYTHONDONTWRITEBYTECODE=1 nice -n 10 \
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B
```

Each log is under `out/q2-recall/`; stdout/stderr combined. Rows below give the
exact arguments appended to that prefix. Class prefix `T` is
`bench.q2_recall.test_recall.RecallPolicies`.

| # | Appended arguments / action | Result | Log |
| --- | --- | --- | --- |
| 1 | `-m unittest T.test_combined_arm_is_rejected_before_any_commands_are_prepared -v` | exit 1, expected red, guard removed | `01-combined-red.log` |
| 2 | same as 1, guard byte-restored | exit 0, 1 test | `02-combined-green.log` |
| 3 | `-m unittest T.test_substituted_manifest_is_rejected_before_any_commands_are_prepared -v` | exit 1, expected red, guard removed | `03-inputs-red.log` |
| 4 | `-m unittest bench.q2_recall.test_recall -v` | exit 0, 4 tests, input guard restored | `04-all-green.log` |
| 5 | `-m unittest T.test_baseline_bytes_cannot_silently_change_under_the_prepared_arms -v` | exit 1, expected red, guard removed | `05-baseline-red.log` |
| 6 | `-m unittest bench.q2_recall.test_recall -v` | exit 0, 5 tests, baseline guard restored | `06-all-green.log` |
| 7 | `-m bench.q2_recall.prepare --inputs /home/elan/code/irl-shield/.tmp/q/frozen-a8a06e3/inputs.json --output out/q2-recall/plan.json` | exit 0, metadata only; no command executed | `07-prepare.log` (empty); `plan.json` is the receipt |
| 8 | `-m .tmp.q2-recall.validate_metadata` | exit 1, relative module names unsupported; code never reached | `08-metadata-failed.log` (transcribed tool output) |
| 9 | `-c 'from pathlib import Path; p=Path(".tmp/q2-recall/validate_metadata.py"); exec(compile(p.read_text(),str(p),"exec"))'` | exit 0, argv flags/shape, compile, bash syntax, source equality | `09-metadata.log` |
| 10 | `python3 .tmp/q2-recall/package.py` | patch roundtrip + exact posthash verification | `10-package.log` |

No test was authored outside `bench/q2_recall`. Full CPU gate held because it
would render synthetic video (`tests/test_quality_bundle.py` setUp/render);
the packet expressly forbids video rendering now. No external service missing
from the checks that ran. This lane has no model/fixture cache provisioned;
root's existing matching cache is available read-only, verified in
`out/q2-recall/cached-weights.json`. Apple Vision build/runtime is untested.

## Handoff and blockers

`out/q2-recall/plan.json` inventories unexecuted quality and five-repetition
NVENC clocked argv for every arm/baseline. Regenerate in root's applied tree
before execution. The detailed screen plan, qualification guards, per-source
GPU-event numerator/denominator, inclusion/exclusion contract and Mac sync are
in `bench/q2_recall/README.md`.

PHONE_TEST_DONE, GPU_RELEASED, V2_FROZEN exact manifest SHA, and active EX queue
were not relayed. No barrier polling or waiting occurred. V2 assets/manifests/
pixels were not accessed. V2 evaluation remains root-only, once, Sunday Nov 1
14:00 UTC. Quality results, screen results, GPU timing, winner and near-miss are
all **null/unmeasured**.

GPU event argv is null: `_session` owns an internal stream, and `detector_for`
filters all unknown options. Genuine event timing needs a verified profiler or
authorized known-userstream seam through fenced `bench/pipeline.py` and the
detector. No host-wall/GPU relabeling or family override. Missing timing blocks
promotion. Future all-arm qualification exceeds the remaining invocation budget
when commands are counted individually; root must account before starting.

Intended patch and exact file hashes: `.tmp/q2-recall/recall.patch` and
`.tmp/q2-recall/post-sha256.json`. Handback/artifact index:
`out/q2-recall/handback.json`. All twelve application files are intentionally
untracked; coordinator applies them. No stage/commit/push. Both yielded owned
exec sessions (84680, 19440) returned exit 0; all others returned completion.
No persistent process or remote process was started. See
`out/q2-recall/process-cleanup.json`.
