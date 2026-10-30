# PR #4 round 1 fixes

Base: `f2f57892b731949d17ce62ba4dcd84d74fb26ab0`, branch
`elannash/q-quality`. This hand-back covers the three accepted round-1
findings and the unrelated bounded-process test failure. Opus owns the
commit, review and merge. Q rendering, corpus judging and accepted quality
numbers remain held until PR #4 merges.

Every sealed bundle now requires an explicit fractional area ceiling and a
nonblank basis receipt reference. `bench.metrics.validate_area_ceiling`
is shared by bundle validation and both benchmark CLIs; it rejects booleans,
nonfinite values and values outside `[0,1]`. `masked_area_pass` applies the
same contract to builders and retained regraders, requiring a finite,
nonnegative measured median at or below the backed ceiling. Missing
configuration is diagnostic only and cannot make `comparison_valid` true.
A basis is a reference retained for human review, not an automatic claim
that its contents justify the chosen ceiling. Q's prepared policy points
to the tracked `bench/gate-1-policy.json`; the older F2 freeze remains
unchanged and must be replaced before launching.

The new area regressions cover missing, percent-valued `15`, negative,
NaN and unbacked ceilings, sealed invalid options before OCR, missing
diagnostic configuration, and a valid `.15` ceiling with a `.57` median.
The invalid bundle cases failed before the fix. The over-ceiling example
was already rejected by the original direct builder; a physical omission
mutation proves its comparison guard is necessary. Five mutations of the
final area code each produced behavioral red results, followed by exact
byte restoration and a green affected test. Both CLIs also have a
regression proving missing basis is rejected before host or fixture work.

Both remaining retained regraders now validate their recorded policy before
reading evidence. A missing non-control lane requires an explicit recorded
fast candidate; a missing, incomplete or conflicting metadata record
raises. Batch rescoring preflights all source cards before creating any
scored output. Neither command fills in historical provenance. Of the 14
historical comparison sources, 12 lack both required provenance fields
and are unsupported; no historical card or count was changed. The other
two explicit-fast records were inventoried, not rescored.

Nine added provenance tests protect source identity before and after OCR,
grade and evidence seals, render binding, policy binding, frozen and copied
inputs, path confinement, and recorded family metadata. Eleven actual
production guard mutations failed behaviorally. Ten have focused restored
green receipts; the eleventh's named test passed in the child's otherwise
failing full suite. The parent integrated all nine tests and audited their
mutation diffs, logs and restoration hashes. Child receipts remain in
their worktrees, linked by the machine-readable proof index.

The child's failing `test_bounded` receipt was a startup race in the test.
Its controlled process had only 0.5 seconds to write its marker before the
cleanup deadline. Injecting one second before marker creation reproduces
`Controlled child never started` with the original test. The test now waits
for group readiness before starting that short cleanup deadline. The same
delay passes, while the existing cleanup-permission and live-descendant
assertions remain. This change is test-only; `scripts/bounded.py` is
unchanged.

Both integrated gates completed with exit 0: 159 main tests (one expected
platform skip), three relay tests and compilation on each host. The Mac's
dedicated `scripts/check` also built the Swift bridge. Linux's gate waited
for the canonical shared host lease behind M2's timed job and then ran in
one clean invocation. The dedicated Mac mirror matched all 14 final code
and test files. No timed run, real OCR corpus score, GPU inference, new
model, dependency, asset or license was introduced by these fixes.

Proof index: `bench/results/pr4-r1-proof.json`. Full local logs are
`.tmp/q/pr4-r1-{linux,mac}-full-gate.log`; area mutation receipts are in
`.tmp/q/pr4-area-proof-final/`; the startup-delay reproduction is in
`.tmp/q/bounded-startup-proof/`.
