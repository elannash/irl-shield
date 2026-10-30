# Fresh held-out one-shot result

**Gate 1 did not pass.** The unchanged B6 diagnostic fallback was rendered once on Linux CUDA/NVENC and judged once on the Mac. No guard-valid tune winner was found; no policy was tuned from these results. The card is ideal/offline with `real_time_verified:false` and `gate_1.pass:false`.

Executed source `26c8db18624731eaf92168e69aa97ddad31abd17`; policy SHA256 `dcbc96c88b0a3c1545a5a04c668446eee1afeb730e901179ffc78063cb91ad5f`; frozen dataset SHA256 `46a4461ca50ac54a4cac564ad81e1bba5c2d990b0cb9976eb473a82e5fcc3cad`. The later test-only Git-fixture repair changes no evaluator, detector, renderer, scheduling, scoring, judge or policy code.

| Criterion | Result | Verdict |
| --- | --- | --- |
| Natural intervals hidden, at least 90% | 106/126, 84.1270% | Fail |
| Synthetic intervals credited hidden, 100% | 14/22, 63.6364% | Fail |
| Median masked area, at most 15% | 13.5967%; p95 50.3944% | Median passes |
| Real video outside masks | Both Zurich variants fail | Fail |
| Aggregate protected, strictly under 2% | 6/900, 0.6667% | Pass |
| Additional per-clip protection, strictly under 2% | Chicago natural 3/150, exactly 2% | Fail |
| D, at most 1 s | Configured 1 s | Configuration only |
| Steady p95, at most 1.3 s; emitted fps at source 30 | Unmeasured by this offline evaluation | Unverified |
| Independent truth engines | Tesseract eng + Vision accurate en-US | Pass |
| Synthetic input controls | All 22 intervals readable in the input | Pass |

Scope is OCR-observed Latin-script text and digits. Independent judges define natural truth and synthetic input controls; every credible output judge, including PP-OCRv5 English, counts a leak. Natural truth uses input confidence at least .9 on two or more frames; output leak threshold is .5. All annotated visible synthetic labels remain truth. Non-Latin coverage is unproven.

Natural counts cover text in both natural and synthetic video variants. There are six five-second clips, 900 frames total, from three fresh licensed sources. The clips were selected from metadata and frozen before privacy inference, OCR or human pixel inspection. All assets are benchmark-only, have no audio and have no demo-readiness claim.

| Clip variant | Natural hidden | Synthetic hidden | Median area | Protected | Real video |
| --- | ---: | ---: | ---: | ---: | --- |
| chicago-wells natural | 30/30 | 0/0 | 2.00% | 2.000% | Pass |
| chicago-wells synthetic | 48/48 | 6/6 | 9.71% | 1.333% | Pass |
| manchester-portland natural | 13/21 | 0/0 | 3.67% | 0.000% | Pass |
| manchester-portland synthetic | 15/21 | 8/8 | 14.80% | 0.000% | Pass |
| zurich-spiegelgasse natural | 0/1 | 0/0 | 11.00% | 0.667% | Fail |
| zurich-spiegelgasse synthetic | 0/5 | 0/8 | 16.71% | 0.000% | Fail |

Manchester has 14 raw natural-text leaks. Neither Zurich variant preserves the real-video guard: 31 LIVE frames fail in its natural clip and 9 in its synthetic clip. Therefore six otherwise-unleaked natural intervals and all eight Zurich synthetic intervals correctly earn zero hidden credit. No raw synthetic output leak was recorded by the judges; that secondary observation does not earn a synthetic pass when video preservation fails. The strict primary result remains 14/22.

The policy, complete scorecard and proof are tracked at [q-final-policy.json](../bench/q-final-policy.json), [q-fresh-heldout-once.json](../bench/results/q-fresh-heldout-once.json) and [q-fresh-heldout-once-proof.json](../bench/results/q-fresh-heldout-once-proof.json). The scorecard SHA256 is `7865083bba59da5c25954b4db97fa27487b3f082355ff15485137f5d61c55272`. Root verified all six bundle/grade seals, 66 sealed artifacts, both spent markers, source/helper identity and one schema 3 judge signature.

The fixed state marker is `.tmp/q/fresh-heldout-once-state/46a4461ca50ac54a4cac564ad81e1bba5c2d990b0cb9976eb473a82e5fcc3cad.started.json`; the transferred corpus retains `JUDGING.started.json` and completed `evaluation.json`. Both physical stages are spent. The tracked scorecard also makes `start()` refuse this dataset after scratch cleanup. They must not be deleted or repeated. Raw encoded inputs/outputs, annotations, masks, source detections, motion, readings and frame guards remain in `out/q-fresh-heldout-once/`.

[FRESH-HELDOUT.md](FRESH-HELDOUT.md) records the historical module workflow, read-only cache override, per-clip locks, preparation rules and dependencies. The root launch script and terminal logs are retained in `.tmp/q/render-heldout-once.sh`, `fresh-heldout-render.log` and `fresh-heldout-grade.log`. Verification of retained bundles uses `python -m bench.quality_bundle --root . verify --directory out/q-fresh-heldout-once/CLIP-VARIANT`; this hashes existing artifacts and runs no detector or judge. Re-encoding on another FFmpeg/GPU may differ from the frozen bytes; transfer the frozen cache rather than rebinding this evaluated dataset.

B12 was rejected on all seven tune clips. It changed neither 298/343 natural nor 44/54 synthetic, while increasing median mask area by 1.1417 percentage points. The [comparison](Q-B6-B12.md) is a separate corpus and is not a delta against this heldout set. Tested giant-confirmation/support/cap ideas were also rejected from exact replay and positive controls; no safe production change was accepted. Padding, input-size, alternative-model and FAST corpus arms remain unrun.

No new packages or models were installed for this final run. Existing private Python 3.11 SDKs, pinned PP-OCRv6 Tiny/Small detector weights and PP-OCRv5 recognition weights were used. Model/dependency licenses remain in `models/manifest.json` and `models/licenses/dependencies.json`; new footage licenses and authors are in [fresh-heldout attribution](../fixtures/fresh-heldout/ATTRIBUTION.md).

This result does not establish native ingest/egress behavior, A/V sync, cadence, realtime latency, walking suitability, Windows support or live Twitch behavior. The integration candidate has separate functional-gate receipts; final-source native HOLD and encoder-in-flight behavior remain unqualified. A proposed next quality experiment is to measure smaller text-component masks and motion-projected unions against the same guards, with the existing positive close-ups retained. That experiment has not been run.
