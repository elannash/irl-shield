# Q4 retained rescore policy

Implementation base: `f2f57892b731949d17ce62ba4dcd84d74fb26ab0`.
Branch: `elannash/q4-retained`. The worktree is locked while its uncommitted
patch and receipts await the conductor's review. No staging, commit, push,
PR, or merge was performed.

## Behavior

Both regraders previously discarded recorded detector metadata when choosing
truth families: `bench/regrade.py:24` and
`bench/rescore_independent.py:42` at the base commit called `policy_metadata`
directly. Missing fast options therefore used the current default. The first
regression reached both actual `main()` entrypoints and failed with
`AssertionError: ValueError not raised` before any implementation edit.

`bench.independence.retained_policy_metadata` now owns this check for both
commands. Recorded `detector_metadata` must equal the metadata derived from
the declared candidate and fast-lane registry policy, including the lanes and
their family union. A conflicting current default raises; it does not replace
the recorded scope. Present but incomplete or null metadata also raises.
The validated recorded metadata supplies the scoring families when present.

Without recorded metadata, a non-control card must contain an explicit
`options.fast_candidate`. The only exceptions are the registered no-detector
controls `unmasked` and `slate`, whose empty families remain valid. Registry
validation still rejects arbitrary `detector_families` options, even for a
control with matching recorded metadata. No name-based family inference or
historical provenance backfill was added.

`regrade` validates before evidence access or output creation. The batch
`rescore_independent` checks the source hashes and policies for every card
before reading any clip evidence or creating the destination. An invalid
later card cannot leave an earlier card's scored output behind.

Both regraders also require `quality_checks.masked_area is True` for a valid
comparison. Missing, null, and failed guards cannot win. This checks the
inherited guard; it does not independently validate a retained area's ceiling
and basis. The parent's new `bench.metrics.validate_area_ceiling` is absent
from this base and remains an integration dependency after patch application.
No sibling-owned metrics code was copied or edited.

## Test scope and proof

The established seam is each command's real `main()` with synthetic source
cards, retained JSON readings, and real scoring and aggregation. Filesystem
observation proves invalid policies fail before evidence/truth access or
score writes; subprocess creation is forbidden at the OCR boundary. This
does not establish real OCR quality, corpus privacy, or performance.

The new tests protect missing provenance, changed defaults, missing lane
metadata, conflicting lane/union metadata, family-list overrides, controls,
valid explicit-fast and recorded mixed policies, and batch preflight. Existing
judge-independence tests exercise scoring families but did not check retained
card provenance. The new tests need no test-only production hooks and assert
literal truth totals and judge scopes through saved scorecards.

Proof is retained in `out/proof/`. The initial missing-provenance and recorded
policy tests failed on the original behavior. The physical mutation then
restored both original regrader files, verified their original hashes, and
failed the regressions for behavioral reasons. Restoring the fixed files byte
for byte returned the new suite to green. `mutation-proof.json` binds the
original, fixed, and restored hashes to the log exit codes. The final proof
is `final-mutation-proof.json`, after the masked-area followup; the earlier
proof remains alongside it. The final restored suite passed all seven new
tests.

Linux functional discovery ran once: 147 tests including the three relay
tests, with one platform skip, passed in `10-linux-functional.log`. That run
preceded the owner's masked-area followup. After that change, the two regrade
tests, seven retained-policy tests, and five judge-gate tests passed in logs
12 through 14. Python compilation passed in `17-linux-compile.log`. This is
functional evidence, not a fresh benchmark score or the integrated Mac gate.
The initial scope launch failed because the runtime bus variables were
unset; supplying their existing user-bus paths fixed the launch before the
first test executed. Fifteen unittest invocations ran, within the 24-run
budget; the failed scope launch is also retained.

All test commands used the existing `models/.venv311` Python and read-only
`.tmp/m2/linux-venv` site-packages under `/home/elan/code/irl-shield`, with
source imported from this worktree. They ran at nice 10 in
`app-t3code-agents.slice`, held the canonical shared
`/tmp/agents/irl-shield/perf.lock`, and used two native threads and one OpenCV
thread. No timed workload was run. The functional queue tests use their own
synthetic queues and locks; the live queues were not changed.

`tests/test_regrade.py` and `tests/test_judge_gates.py` needed no fixture
migration at this base: the former uses no-detector controls and the latter
already declares explicit fast candidates. Neither file was edited.

## Historical provenance limit

`out/retained-history.json` inventories only the 14 source cards named by
`bench/results/m1-tune-comparison.json`, reading the source cards under the
root checkout without reading evidence or rescoring. All source hashes match
the comparison. Twelve cards have neither recorded metadata nor an explicit
fast candidate and are unsupported by this rescore path. The other two
declare a fast candidate; the inventory alone does not establish their
scoring validity. No source card, historical count, or comparison was changed.

## Handoff boundary

No real-corpus rescore, OCR, GPU, Mac, model download, install, secret access,
account action, live queue mutation, or network publication was performed.
No third-party dependency, asset, model, or license was introduced. Existing
fixtures remain benchmark-only, without music, and are not demo-ready assets.

QHEAVY and accepted quality numbers remain held until PR4 merges. The
conductor still owns integration with the sibling area/provenance changes,
the integrated Mac/Linux gate, cross-vendor review, commit, and PR lifecycle.

## Parent integration

Opus applied the five source, test and documentation files to
`elannash/q-quality`; the child's ignored proof files were not copied.
The retained originals and mutation receipts remain at
`/home/elan/.t3/worktrees/irl-shield/t3-36250274/out/proof/`, with the
inventory at that worktree's `out/retained-history.json`.

The integrated regraders now call the parent's shared
`bench.metrics.masked_area_pass` before evidence access. An inherited
`masked_area: true` is insufficient: the ceiling must be a finite fraction,
have a nonblank basis receipt reference, and bound the finite measured
median. The existing inherited guard must also remain exactly true.
The synthetic retained fixtures now include a basis reference and literal
median. These are integration edits after the child's frozen patch.

The integrated gate and proof index are recorded in
`docs/PR4-R1-FIXES.md` and `bench/results/pr4-r1-proof.json`. The child's
historical gate counts above are not the integrated gate result.
