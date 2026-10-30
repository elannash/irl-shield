# Blind vision panel

This local harness creates blinded grading packs and validates two independent
returns. It invokes no model, SDK, OCR, GPU job or network service. Actual grading
belongs to fresh blinded sessions: root's Sol 6.1 xhigh and Opus's Opus 5.5 high.
The implementation lane does not grade its own pack. A directory on the same
machine is not a sandbox: the dispatcher must attach only the public allowlist,
without repo access, history, private files or other grader returns.

## Selection scope and receipts

Effectiveness and pairwise comparisons use **natural seven-clip tune only**.
Spent-v1 can remain a separately labeled development analysis outside this
harness; it is not silently pooled with tune. Synthetic overlays are regression
controls only, including licensed raw traps; they never enter panel arm means,
pairwise selection, agreement denominators or the final panel bar. Fresh-v2 is
rejected before media access, with no one-shot override. Sunday access requires
separate root orchestration. Owner media is unsupported here and rejected before
opening; a later adapter requires explicit authorized shielded path/hash inputs.
Owner raw never becomes a trap. Unknown/unlicensed input is rejected.

`legacy-plan` binds existing outputs to the tracked final policy, sealed bundle,
exact input hashes and frozen fixture manifest. Its arm is explicitly the
`a8a06e3` opaque/phase **diagnostic fallback**. It is not the new W1 tracking and
frosted policy. W1 output and lighting-stress variants remain pending until exact
policy/source/output receipts exist. The baseline plan does not imply acceptable
privacy or speed. No detection, masking, rendering pipeline or OCR is rerun.
CPU-only extraction and metadata-free re-encoding use already provisioned PyAV
and Pillow, imported lazily. No new dependencies. Existing PyAV/FFmpeg and Pillow
license records remain the owning dependency records; fixture attribution stays
in `fixtures/ATTRIBUTION.md`, outside the blinded attachment.

Trusted plans contain assets, items, pairs and per-arm metric receipts. Validation
first checks **every** asset's split/origin/license/path policy and all item/trap
rules. Only then does it hash receipts/media. Media must match `input.mp4` or
`masked.mp4` in the same sealed bundle; bundle policy must exactly match the
frozen candidate/options. Input manifest must bind to the fixture manifest.
Receipts are rechecked after extraction and again after both sealed returns.
Trusted manifest/license verification is an operator responsibility: hashes bind
supplied provenance; this is not a license discovery service.

## Public and private boundary

Public directory: neutral random 128-bit PNG/MP4 names, `items.json`, `rubric.md`,
`response.schema.json`, and nothing else. IDs and presentation order use system
randomness. PNGs are new RGB images with no metadata; MP4 clips are new, silent,
two-second H.264 videos retaining only neutral muxer tags. Arm names, policies,
source names, scores, GPS, fixture attribution and other grader outputs never
enter this directory. Semantic clues visible in actual video remain observations.
The pack digest hashes canonical items.json excluding its own digest field;
items.json includes hashes of every other allowlisted file. Verification rejects
extra files, directories, symlinks, filename changes and hash drift.

Private sibling directory: `SEALED.json` contains the source/policy manifest,
item/frame mappings, predeclared trap expectations and pairwise arm roles;
`seal.json` contains its SHA-256. Record the map hash independently at dispatch.
Scoring requires that pinned hash, not merely the adjacent seal. Public and
private roots cannot contain each other. Generated files are read-only and
created exclusively; state is tamper-evident, not OS-enforced immutable against
the owner. A partially generated pack without a complete private seal is unusable.
Keep all generated packs, maps, responses and reports in ignored `out/` or `.tmp/`.
Only an owner-reviewed small summary may later become tracked source.

## Commands and lifecycle

Run these commands in root's scheduled canonical SH queue with its provisioned
SDK and resource envelope. These are local commands, not instructions to schedule
GPU work. Never run the full gate without root's explicit scheduling.

```
python -m bench.vision_panel legacy-plan ROOT FINAL_POLICY OUT/plan.json
python -m bench.vision_panel build OUT/plan.json OUT/public OUT/private
python -m bench.vision_panel verify OUT/public
python -m bench.vision_panel begin OUT/public OUT/round SOL_IDENTITY OPUS_IDENTITY
python -m bench.vision_panel finish OUT/public OUT/round 0 SOL_RETURN.json
python -m bench.vision_panel finish OUT/public OUT/round 1 OPUS_RETURN.json
python -m bench.vision_panel score OUT/public OUT/private OUT/round PINNED_MAP_SHA256
```

`begin` creates an exclusive round roster, random per-grader start IDs and start
timestamps. Pass each grader only its own start ID, exact identity, pack digest
and public files. Identity must name the actual independent session/model; the
coordinator verifies this operationally. The harness rejects equal identities,
including case variants, but cannot detect one model lying under two aliases.

`finish` bounds and validates JSON, rejects missing/unknown/duplicate IDs,
unknown/missing fields, nonfinite/out-of-range scores, wrong digests/start IDs,
missing completion and malformed readable observations. It stores a canonical
return plus an exclusive read-only finish receipt binding start/output hashes
and timestamps. Duplicate JSON keys are rejected. No returned string becomes a
path, command or HTML. There is no automatic retry, replacement, overwrite or
replay; a void experiment needs a new pack/round and preserves the old evidence.
Both complete finish seals are required before **any private map access**.
Implementation, starts, public files, private map and source receipts must still
match. Thresholds are sealed before the returns, not tuned from their contents.

## Traps and pairwise semantics

Every pack needs at least eight honest items and at least 15% trap items, including
licensed raw (privacy <=3), all-black (watchability <=3) and exact duplicate media.
Raw owner media is rejected. Duplicate item axes may differ by at most one point;
readable sets must match after case/whitespace normalization, retaining kind and
time offset. Free-form location inference need not match wording. Duplicate
controls, raw and black items are excluded from arm effectiveness scores.
Either grader failing **any** trap voids the whole round: no accepted arm scores
or win rates. Trap checks, all readable hits and original contradictory responses
remain in the report. Raw traps should use the predeclared synthetic sign input
so their readability is established by fixture construction, not post-hoc tuning.

After staged ablations and greedy selection, root prepares the top-three natural
tune pairwise round. Each pair matches source, variant, kind and time across
current-best/candidate arms. Left/right is randomized; hidden arm roles remain
in the map. Every pair round requires an independent duplicate comparison with
reversed presentation. It must pick the same underlying item or tie per axis;
this is checked separately from absolute duplicate-item tolerances. Duplicate
comparisons are excluded from win-rate denominators. Reports show wins, losses,
ties, total comparisons, wins/total and wins/decisive (null for all ties).

## Reports, joins and uncertainty

Per-arm means and 95% intervals are reported per grader and pooled per axis over
honest natural items, weighting each sampled item equally. The preregistered
percentile bootstrap resamples **original source clusters**, carrying all their
frames, variants and both graders together, 2,000 times with a fixed seed. Fewer
than five source clusters yields a null CI with an explicit reason. These are
descriptive ordinal summaries of this tune population, not a safety estimate.
Intergrader agreement reports absolute differences, exact/within-one counts and
readable-set agreement with explicit honest denominators. All readable hits,
including controls and contradictions, map back to arm, source hash, clip,
variant, source frame and grader as data-only work items.

Each arm includes join keys: arm, measured source commit(s), exact frozen policy
hash(es), input hashes, output hashes and metric receipt path/hash. Metrics are
`natural_hidden` (fraction), `flicker` (rate), `area` (masked fraction), `realvideo`
(real-video fraction), `gpu_ms` (per frame), `cpu` (one-core percent), `max_fps`,
`e2e_latency_including_delay` (seconds, including D), plus panel privacy,
watchability and readable-hit counts. Missing measurements remain null. A metric
join receipt has exact arm/source/policy/input/output identities, natural-tune
scope, metrics, and per-metric evidence path/hash plus JSON pointer. Values are
checked against those receipts; a hash is never invented to stand in for a result.
Mixed natural/synthetic area or real-video aggregates cannot be natural metrics.
For the retained baseline only the explicitly natural hidden fraction can join
from its existing scorecard; other measurements remain null until root supplies
properly scoped immutable receipts.

Both graders must independently meet mean privacy >=9 and watchability >=8 for
the absolute panel bar. `absolute_panel_bar` does not establish OCR correctness,
real-video validity or speed. OCR hard gates and no-regression requirements remain
unchanged. Production promotion is always false; the panel cannot override OCR
or performance guards, trigger production changes or retune from fresh-v2.
