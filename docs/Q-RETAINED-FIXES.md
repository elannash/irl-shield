# Retained-judging followups after PR #3

Implemented on `elannash/q-quality`, based on `62b536f`. Queue accounting is
already a separate `815b420` commit. The producer/stop fixture repair is the
separate test-only commit `e698aac`. This hand-back covers the two retained
judging findings; it contains no fresh corpus score.

`bench.clocked_bench.score_video` now validates the recorded lane candidates
before opening video or invoking OCR. Families come from those registered
models. A missing fast-lane model raises. A current policy/default conflicting
with the recorded model also raises, following the review's fail-closed
alternative: aggregate annotations cannot silently describe another policy.
Recorded family metadata, when present, must agree. Earlier retained runs
record model keys without family metadata; the explicit registry identifies
their families. No-detector controls have no missing detector to reconstruct.

The regression uses actual encoded input/output frames. It reproduces a mixed
Vision/PP run after the fast default returns to Vision, proves rejection
before OCR, checks the recorded mixed scope with its matching policy, checks
historical model-only metadata, and rejects missing fast-lane provenance.

`bench.rejudge_retained` derives its cache scope from the actual judge's cache
identity. A fourteen-variant synthetic sealed-file test drives the real
re-judge CLI, scorer and aggregator with a pixel reader at the OCR boundary.
It supplies schema 9, so pinning another current version cannot satisfy it.

Proof: `.tmp/q/retained-judging-proof-final/proof.json`. Restoring each original
production file causes its regression to fail (`ValueError not raised`, and
`cache-v9` absent). Exact byte restoration returns each test to green. The
initial narrow environment lacked pytesseract; that import error is not a red
proof. Behavioral proof and final gates use the existing complete environment.

Final gates: Linux and Mac each passed 138 main tests (one platform skip),
three relay tests and compilation. The Mac also built the Swift bridge.
Logs are `.tmp/q/quality-final-{linux,mac}-gate.log`; hashes and source pins are
in `bench/results/q-retained-proof.json`. Five main tests belong to the separate
experimental harness; these followups alone bring committed discovery to 133.
Linux adds the existing `.tmp/m2/linux-venv` site-packages for PyAV; no install
was needed. The Mac gate uses its own `~/code/irl-shield-q-quality` mirror and
the shared performance lease, preserving the old running Mac queue source.

An intermediate Linux gate exposed the existing retry fixture's ten-second
runner deadline (`pending` rather than `exhausted-contended`). The followup
sets sixty-second headroom for that fixture only. Production queue deadlines,
sampling, assertions and the separately tested hard-stop contract are unchanged.
Its failed full log and focused green are retained under
`.tmp/q/retained-judging-proof/linux-full-gate-final.log` and
`.tmp/q/producer-stop-proof/ack-headroom-green.log`.

Fresh schema-3 corpus judging, baseline rendering and Q3 acceptance have not
started. These followups and the experimental harness retain separate review
and commit boundaries. No new package, model, dataset or license was introduced.
