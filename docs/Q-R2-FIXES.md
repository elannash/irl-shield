# Q preparation: deferred PR4 round-2 checks

Base: merged `main` at `a9b4622`, branch `elannash/q-hill-climb`.
These checks precede the first reported Q result. Opus owns the commit.
No detector, mask, motion, scoring definition or historical card changes.

The added bundle regression renders and grades all fourteen synthetic
test variants through the existing encoded-pixel fixture. The sort-first
bundle seals a ceiling of `1.0`; the other thirteen seal `0.01`. Each
bundle is individually valid. Aggregation must reject the mixed policy
and leave no scorecard. The existing uniformly resealed-grade test does
not cover this cross-clip contract. Removing the real cross-clip guard
makes the new regression fail with `ValueError not raised`.

The existing retained-area table now tests both real regrader entrypoints
with a stored pass but no basis, and with a stored pass whose measured
median is `.57` against a `.15` ceiling. Each must set both the area guard
and comparison validity to false while every other comparison guard is
true. A valid backed `.1` median remains a passing control. Independently
forcing either regrader's fresh-area result true makes the extended table
fail with `True is not False`.

Both CLI tests now retain stderr and require the basis-receipt diagnostic
as well as exit 2 and no host work. Replacing each CLI's message with an
unrelated parser error makes its assertion fail. The unused local `area`
in `clocked_bench.aggregate_card` is removed.

These tests use the owning public interfaces and extend the existing
fixtures and tables. They add no production seam. Their realistic bugs
are a removed corpus policy guard, trusting a stored area flag without
rechecking the receipt, and accepting any unrelated parser rejection as
proof of early area validation.

All 18 affected tests pass. Five physical production mutations produced
the named behavioral failures, with byte-for-byte restoration followed
by green focused runs. Raw diffs and logs are in
`.tmp/q/pr4-r2-proof/`; the driver is `.tmp/q/prove-pr4-r2.py`.
The durable source, mutation and gate index is
`bench/results/q-r2-proof.json`.

The Linux and dedicated Mac gates both exited 0: 160 main tests (one
platform skip), three relay tests and compilation on each, with Swift
built on the Mac. Their current contract is the pre-existing root suite
plus relay suite. They do not yet include the 55 Twitch tests:
the conductor assigned that known gate gap, a unified pinned Python 3.11
environment, and clean Linux/Mac verification to the integration lane.
No Twitch-inclusive gate pass is claimed here. Its CLI assertion is not
run by design under the approved local-only boundary, citing M3's merged
protocol receipts.

No Q score, model inference, real OCR corpus run, performance receipt,
dependency installation, new asset or model is produced by this change.
