# Q4 bundle provenance guard tests

This test-only hand-back starts from `f2f57892b731949d17ce62ba4dcd84d74fb26ab0`
on `elannash/q4-provenance`. Its final production files must match that base
byte-for-byte. Opus owns application, integration, commits and review. QHEAVY
and accepted Q numbers remain held until PR4 merges.

The tests call the existing public `grade`, `aggregate`, `verify` and
`recorded_policy_metadata` interfaces. The bundle tests import
`test_quality_bundle` as a module and reuse only its setup/render/corpus
helpers; they do not import or inherit its TestCase, so discovery does not
run the base suite twice. The fixture encodes four synthetic 96×48 frames
with local FFmpeg/libx264. Its detector and OCR reader are synthetic. Real
video decoding, saved raster mask validation, scoring, independent truth,
ALL output leak semantics and aggregate gates run unchanged. No model or
real OCR engine is loaded.

## Why each test belongs here

Each row answers the test gate's behavior, realistic bug, owning layer and
coverage gap. Every test uses an existing interface; none adds a production
export, flag or reset hook.

| Test | Behavior and realistic bug | Owning layer and existing coverage gap |
| --- | --- | --- |
| Source before OCR | Both pipeline and orchestrator source identities must match. An omitted pre-check starts the reader on a foreign source. Rejection leaves reader count zero, no evidence and no grade. | `grade`; the existing bundle test rejects changed mask artifacts, not source identity. |
| Source after OCR | A source change during reading must reject after all eight synthetic reads and leave no grade or grade seal. | `grade`; the existing render-time source check does not protect the grading interval. |
| Aggregate receipt seals | Changed grade bytes, evidence bytes, or the grade's render SHA reject without writing a scorecard. A resealed wrong render link isolates the bundle-binding check from the grade-byte check. | `aggregate`; existing relocation and mixed-input tests do not tamper with these three links. A valid 14-variant positive control exercises the real reducer before tampering. |
| Grade versus plan policy | Uniformly editing and resealing every grade's options cannot replace its rendered policy. Uniform edits deliberately pass the cross-grade policy comparison. | `aggregate`; existing tests compare corpus identity, not grade versus plan options. |
| Frozen manifest | Updating the artifact checksum after changing `inputs.json` cannot rebind the frozen input-manifest identity. | Public `verify`; the existing snapshot test protects render-time copying rather than later resealing. |
| Copied input | Resealed changed source or truth bytes cannot disagree with the frozen row. | Public `verify`; the existing copy-race test protects render-time input copies. |
| Confined artifact paths | Absolute, parent-directory and symlink escapes reject even with correct artifact hashes. | `verify` through `checked_file`; existing tampering stays inside the bundle. The original local bundle verifies again afterward. |
| Recorded families | Fast and accurate family metadata must match their registered model keys. | Public `recorded_policy_metadata`; existing `score_video` wiring covers changed defaults and missing fast lanes, but not mismatched family metadata. A literal mixed-policy positive control checks both lanes and their union. |
| Missing accurate lane | A declared accurate model cannot stand in for a missing recorded accurate-lane receipt. | Public `recorded_policy_metadata`; existing retained tests cover only absent fast-lane provenance. |

Source fingerprint substitution represents external environment identity;
orchestrator checks use a temporary copy and module file metadata. The
post-OCR reader changes that external identity while the actual scorer reads
the encoded movies. These cases observe rejection and reader counts, rather
than asserting calls to an internal guard or mocking the scorer.

## Proof and limits

Receipts live in `out/proof/q4-provenance/`. `run-tests.py` enforces the
original 24-call budget and the earlier of the original Q deadline and 45
minutes from this child's start. Calls include nested mutation tests. Every
invocation holds a shared lease on `/tmp/agents/irl-shield/perf.lock` and runs
at nice 10 in `app-t3code-agents.slice`, with native worker limits of two and
OpenCV set to one thread. These are untimed functional tests, not benchmarks;
no queue is changed.

The parent will add a valid `area_ceiling_basis` to the shared base fixture
before integration. This worktree intentionally retains the F2 production
validator and shared fixture unchanged. No area validation is bypassed.

Final mutation outcomes, Linux functional results, source hashes, patch and
post-apply manifest are recorded with the completed hand-back. Native Mac,
real OCR, models, GPU, quality/performance measurements and the integrated
Mac/Linux gate remain outside this child's scope. Existing fixture footage
remains benchmark-only, without music, and is not made demo-ready. No new
dependency, dataset, model, asset or license is introduced.

## Final receipts

The initial focused invocation passed all nine new tests. Eleven distinct
production guards then produced behavioral red results, with an actual
single-guard diff and changed source hash for each. The first ten have a
focused restored-green invocation. The eleventh (grade versus plan policy)
is restored and its test passes in the final Linux suite; that suite is red
because of a different existing test. The suite filename contains the
planned `restored-green` label, but its recorded exit code is **1**, not a
green gate.

| Guard | Red observation | Restoration receipt |
| --- | --- | --- |
| Pre-OCR source | Pipeline and orchestrator cases each read eight times instead of zero | `mut-01-pre-ocr-source-restored-green.log` |
| Post-OCR source | Both cases incorrectly return a grade instead of raising | `mut-02-post-ocr-source-restored-green.log` |
| Grade SHA | Changed grade bytes incorrectly aggregate | `mut-03-grade-sha-restored-green.log` |
| Evidence SHA | Changed evidence bytes incorrectly aggregate | `mut-04-evidence-sha-restored-green.log` |
| Bundle binding SHA | A resealed grade bound to another render incorrectly aggregates | `mut-05-bundle-binding-sha-restored-green.log` |
| Artifact confinement | Absolute, parent and symlink escapes all verify | `mut-06-artifact-confinement-restored-green.log` |
| Recorded families | Both inaccurate fast and accurate family declarations are accepted | `mut-07-recorded-families-restored-green.log` |
| Recorded accurate candidate | A missing accurate lane is accepted | `mut-08-recorded-accurate-restored-green.log` |
| Frozen input manifest | A changed, artifact-resealed manifest verifies | `mut-09-frozen-input-manifest-restored-green.log` |
| Copied input binding | Changed, artifact-resealed source and truth both verify | `mut-10-copied-input-binding-restored-green.log` |
| Grade versus plan policy | Uniformly resealed changed options incorrectly aggregate | That named test passes in `24-linux-functional-restored-green.log`; whole suite exit 1 |

The first mutation attempt failed on the distinction between pre- and
post-OCR error messages. The test was strengthened to assert the reader
count before matching the message, then the same physical mutation was run
again. The initial test snapshot, failed proof-driver attempt and both red
logs are retained. They are not omitted from the budget: **24 of 24 test
invocations were used**, including the combined main/relay invocation.
No further tests were run after reaching the cap.

The single final Linux functional invocation collected and ran **150 tests**:
147 main tests and three relay tests. It finished with **one failure, zero
errors and one expected macOS/VideoToolbox skip**. All nine new tests, all
five existing `QualityBundle` tests (discovered once), and the three relay
tests pass. Compilation of `bench`, `fixtures`, `models`, `shield` and `relay`
succeeded. There was no dependency/import failure; the main interpreter
reused the installed relay environment's PyAV package without installation.
See `linux-functional-summary.json` and the full log.

The sole failure is outside these owned paths:
`test_bounded.ProcessDeadline.test_permission_error_is_ignored_only_after_group_members_have_exited`,
subcase `live=True`, at `tests/test_bounded.py:35`, reports
`Controlled child never started`. The fixture allows 0.5 seconds for that
child (`tests/test_bounded.py:29`). This receipt establishes the observed
startup failure; it does not establish its cause. The test and production
process runner were not edited or retried. The parent must run the
integrated gate and resolve this failure within its scope.

Both physically mutated production files match their base bytes again:

| Source | SHA-256 |
| --- | --- |
| `bench/quality_bundle.py` | `9adb5d1eab18030723294113857908fd2058bceb2e8f7341468a6138170e72c2` |
| `bench/clocked_bench.py` | `111d5f189068d77e4e33ea9117f301a48f696bb08951439d90e83005bcddbac8` |

No tracked production diff or staged change remains. The only non-ignored
changes are the two new test modules and this document. `out/handback.json`
and the complete patch carry the ignored proof artifacts explicitly.
`post-apply-sha256.json` hashes every delivered payload file except itself
and patch transport metadata, avoiding a recursive self-hash. The patch
includes the manifest and every new payload file; its own bytes and
`delivery.json` are transport metadata. Opus can apply the patch without
cross-worktree file copies and compare the manifest after application.

All 24 owned systemd test scopes are inactive/dead with empty control
groups, verified in `owned-scopes-final.json`. No test process is retained.
The dedicated worktree is locked for these uncommitted receipt references.
No staging, commit, push, PR, merge, network publication, install, Mac work,
real OCR, GPU work, model download, secret access or live-queue change took
place.

The owner's area-gate steer is compatible with these tests: each bundle
inherits the shared module fixture and never replaces its configuration.
The parent's `area_ceiling_basis='unit:sealed-known-mask-pixels'` therefore
flows into every new render after integration. Running these tests against
the parent's uncommitted area validator remains unverified here. The F2
shared fixture and area production files were left unchanged.

## Parent integration

Opus applied only the two test modules and this document to
`elannash/q-quality`. The 89 ignored proof payloads, including the generic
`out/handback.json`, were deliberately excluded. Their originals remain at
`WORKTREE_t3-96d4fa2d/out/proof/q4-provenance/`;
that worktree's `out/handback.json` indexes them. No root output was
overwritten.

The parent supplied the shared fixture's area-basis reference. A delayed
startup reproduction confirmed the bounded-process fixture race: adding
one second before the controlled child writes its marker fails the old
test with `Controlled child never started`. The test now starts its short
cleanup deadline after the controlled group reports readiness; the same
delay passes. Production `scripts/bounded.py` is unchanged.

See `docs/PR4-R1-FIXES.md` and `bench/results/pr4-r1-proof.json` for the
integrated gate and the parent-audited proof index. The earlier failing
child gate and its labels remain unchanged.
