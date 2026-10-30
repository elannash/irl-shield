> Root integration update: the legacy mixed-policy constructor case is now covered; see the root closure below. The original lane limits remain documented as history.

# P2 judge-independence gates

The new `tests/test_judge_gates.py` covers the real scorecard constructors and
CLI entry points without OCR, model loading or performance measurement. Four
builders reject PP accurate plus Vision fast with Tesseract-only independent
truth. `run.main` has supported-policy reporting coverage, with the mixed-policy
limit below still unresolved. This handback does not claim the packet's complete
five-builder mixed-policy requirement is met.

The worktree started clean at merge commit
`631dc5b9bf7cb90c84f0d4aebf430fdcf24eb89c`. Its tree,
`16d6dc319ce914d898863cb02c9c55c2799a203e`, equals the tree of
`0648e0f64d599b223d101f6643ed7d75a36331e3`. The branch was renamed in place to
`elannash/q-p2-gates`. Changes remain uncommitted.

The reviewed finding is `claude:independent-judges-gate-untested` in
`/tmp/claude-1000/agents/twitchcon-hackathon/conductor/pr1-review-claude-r2.json`.
Before edits, `git grep -n independent_judges -- tests` returned no matches.
Source inspection reproduced the existing, untested enforcement at
`bench/clocked_bench.py:417-432`, `bench/offline_quality.py:426-442`,
`bench/run.py:212-221`, `bench/regrade.py:63-68`, and
`bench/rescore_independent.py:84-91`. No missing production independence check
was found in those paths. Production files remain byte-identical to HEAD.

The shared evidence has one natural interval and one visible synthetic interval
on two frames. Each input contains readings tagged with the three registered
judges. Outputs have no readings, input controls succeed, and pixel guards pass.
The tests call real `score_records`, `policy_metadata`, `annotate_card` and final
gate construction. Expected truth judges and privacy outcomes are literal
requirements, not values computed by the gate under test. Mixed-family cases
must expose only Tesseract as truth and retain all three output leak judges.
Existing scoring tests own leak/filter semantics; this lane owns the builders'
acceptance wiring.

Each rejection case has a same-family PP fast-lane control with two independent
truth judges. Every other substantive check is asserted true. The clocked case
also has three synthetic clip identities, non-pilot heldout flags, an area
ceiling with a basis, a clean queue receipt and a healthy sustained fixture
accepted by the real `clock_guards`. These are synthetic acceptance inputs,
not heldout benchmark results. The control passes final Gate 1; changing only
the declared fast lane makes it fail.

| Builder interface | Protected behavior and realistic regression | Meaningful verdict |
| --- | --- | --- |
| `clocked_bench.aggregate_card` | A mixed policy must fail even when every other requirement passes; deleting or ignoring its independence gate otherwise accepts it. | `gate_1.independent_judges=False`, `gate_1.pass=False`, eligibility remains true. |
| `offline_quality.build_scorecard` | A single independent judge cannot establish a valid privacy comparison; omitting the conjunction otherwise accepts it. | `quality_checks.independent_judges=False`, `comparison_valid=False`. This builder has no independence key under `gate_1`. |
| `regrade.main` | Retained evidence must recompute independence and reject a comparison with only Tesseract truth. | Both independent keys are false and `comparison_valid=False`. |
| `rescore_independent.main` | Reproducing pooled counts and prior comparison provenance cannot bypass independent-judge acceptance. | Both independent keys are false and `comparison_valid=False`. |
| `run.main` | The supported single-family CLI must retain its independence report; deleting the report is detected. | `gate_1.independent_judges=True`; final eligibility/pass remain false by design. The mixed-policy case is pending. |

`tests/test_judge_independence.py` previously tested family selection at the
scoring interface, not these builders. `test_offline_quality` covered protection
rejection, `test_regrade` covered retained mapping and units, and clocked tests
covered performance guards. None exercised the builder independence verdict.
The new tests reuse the existing warmed-performance and sustained-receipt
fixtures rather than introducing parallel performance simulators. There is no
test-only production export, switch or reset hook.

The legacy/offline builders hard-code `gate_1.eligible=False` and
`gate_1.pass=False`. Their tests assert those values, but their privacy mutation
proof concerns `comparison_valid` or the independent key. A constant final
failure does not prove that final Gate 1 enforces independence.

`run.main` accepts no `--fast-candidate` argument and constructs its own options
at `bench/run.py:119-145`. Every selectable registered policy there leaves at
least two declared independent judges. Its pipeline constructs a single
detector at `bench/pipeline.py:29-45,65-69`. Patching policy metadata, the parser,
or `annotate_card` would violate this packet's fixture constraint. Merely adding
a fast-lane flag would declare a lane the serial pipeline never runs, so that
is not proposed as a production fix.

Root can resolve the remaining coverage gap without changing detector policy
by extracting the existing `run.main` gate construction into a production
function called by `main`. A minimal extraction would move
`bench/run.py:208-221` into `build_gate(card)`, read `results` from `card['clips']`
and `sustained` from `card['sustained']`, retain every existing expression, and
replace the moved block in `main` with `build_gate(card)`. The mixed case can
then exercise that actual constructor using the same evidence and options as
the other builders. This remains a proposed interface change for root, not a
production patch applied by this test-only lane. Until root resolves it, the
requested negative `run.main` coverage and its privacy acceptance mutation
proof remain unfinished.

Six accepted mutation receipts are in `out/p2-gates/mutations.json`. Each receipt
records the original, mutated and restored source SHA-256. Source copies live
under `.tmp/p2-gates/<mutation>/`; mutations were asserted to match once, read
back, diffed, tested with `-B`, restored byte for byte, and retested green.

| Private mutation | Red observation | Restored observation |
| --- | --- | --- |
| `clocked-key` | Removing the gate key accepts the mixed policy and fails the privacy acceptance assertion. The positive control also detects the missing report. | `clocked-key-restored-green.log` passes. |
| `clocked-conjunction` | Ignoring the independent key in final `all` makes mixed `gate_1.pass=True`. | `clocked-conjunction-restored-green.log` passes. |
| `offline-conjunction` | Removing independence makes mixed `comparison_valid=True`. | `offline-conjunction-restored-green.log` passes. |
| `regrade-conjunction` | Removing independence makes mixed `comparison_valid=True`. | `regrade-conjunction-restored-green.log` passes. |
| `rescore-conjunction` | Removing independence makes mixed `comparison_valid=True`. | `rescore-conjunction-restored-green.log` passes. |
| `synchronous-key-complete` | Removing the supported policy's independent key fails its reporting assertion. This is not a mixed-policy acceptance proof. | `synchronous-key-complete-restored-green.log` passes. |

All red logs and exact one-change diffs use those prefixes in `out/p2-gates/`.
The command ledger is `out/p2-gates/test-invocations.jsonl`. Diagnostic attempts
also consume the test budget: the first clocked mutation had a positive-control
KeyError before its missing-key assertion was improved; the first synchronous
import lacked `pytesseract`; its first complete-environment run exposed an
unmocked `uname -p` environment probe; its first private copy omitted fingerprint
input `requirements.txt`. Those attempts are not accepted privacy proofs. The
first clocked diagnostic's log path was reused by its corrected red run; its
original invocation remains in the ledger.

Commands run with native worker limits of two, OpenCV threads set to one,
`nice -n 10`, `MemoryMax=2G`, `MemorySwapMax=0`, `TasksMax=64`, and
`app-t3code-agents.slice`. The first four builders used the existing Linux probe
venv; synchronous coverage and the final suites use the existing complete venv
at `/home/elan/.t3/worktrees/irl-shield/t3-1b7da09d/.tmp/fast/.venv/bin/python`.
Bytecode writes are disabled. No dependency or model was installed, no OCR or
GPU work ran, and no production/non-test records were created. These synthetic
assets are benchmark-only, have no music, and are not demo assets. No new third
party dependency, dataset or license was introduced.

Final Linux functional results, source hashes, file hashes, scope checks and
unfinished work are recorded in `out/p2-gates/handback.json`. Parent owns the
full Mac gate, integration, the `scripts/check` exclusion, Q1-Q3 measurements,
commits and review.


## Root closure of the serial constructor gap

Root extracted the existing gate block into `bench.run.build_gate(card)` and
made `run.main` call it. No threshold, detector policy, eligibility, or final
reference-only verdict changed. `tests/test_legacy_judge_gate.py` supplies a
PP-only control and a mixed PP/Vision policy with every other substantive
check passing. It asserts the actual independent-judge key is true/false, and
that this superseded serial path remains ineligible in both cases. The existing
lane CLI test exercises main-to-constructor wiring.

A physical mutation makes the legacy independent-judge report unconditionally
true. The mixed case fails with `True is not False` and the named single-truth-judge
assertion; exact source restoration passes. `.tmp/q/legacy-gate-mutation.json`
and its red/green logs retain the source hashes. This is report/enforcement-key
coverage for a permanently disabled reference path, not a claim that the legacy
path can ever pass a realtime gate. The four enabled comparison/clocked builder
mutation proofs above establish their actual acceptance decisions.

The initial integrated Mac gate passed. The initial Linux gate caught a timing
assumption in the existing queue test: a synthetic busy flag lasted150ms and
could disappear before the observer ran. Its fixture now keeps that flag until
the observer acknowledges it. A controlled300ms observer delay reproduces the
old fixture failure and passes with acknowledgement, without changing production
queue behavior. Receipts: `.tmp/q/queue-fixture-delay-proof.json`. Final integrated
gates are run after this fixture correction.
