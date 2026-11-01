# PR #1: round-one corrections

All accepted blockers and the conductor's truth/leak correction are fixed on `elannash/m1-bench`, based on `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`. Changes remain uncommitted for Opus review. No Q policy measurement has started.

## Primary contract: independent truth, all-judge leaks

Candidate metadata explicitly declares every detector family and the default/overridden fast lane. Natural truth and synthetic input controls exclude all families used by either lane, before deduplication and interval formation. PP policies use Tesseract and Vision for truth; Vision policies use Tesseract and PP. Mixed PP+Vision reports only Tesseract for truth and fails the minimum-two-independent-truth-engines guard. Unknown candidate/input-reader provenance fails explicitly.

**Every credible output reading counts as a leak, including a reading from the detector's own family.** More output judges can discover additional leaks; they cannot hide a leak. Independence prevents bias in the input denominator, while output leak sensitivity uses all engines. Scorecards record `truth_judges` and `output_leak_judges` separately. Synthetic annotations always remain the denominator; the independent input OCR is a discrimination control, not a filter on annotations.

The table rescored the same retained raw readings without new OCR, processing or timing. Each metric cell is **natural; synthetic**. The third scoring column is primary. The former independent-both policy is preserved as superseded diagnostic history. PP and Vision have different truth denominators; fractions must be read with that scope.

| Card | Pooled truth + all leaks | Independent truth + independent leaks (superseded) | Independent truth + ALL leaks (PRIMARY) |
| --- | ---: | ---: | ---: |
| auto-final-offline-vision-union-a30 | 370/435 (85.06%); 48/54 (88.89%) | 201/246 (81.71%); 48/54 (88.89%) | 200/246 (81.30%); 48/54 (88.89%) |
| auto-final-offline-ppocr-v5-mobile-a30 | 385/435 (88.51%); 46/54 (85.19%) | 310/343 (90.38%); 46/54 (85.19%) | 304/343 (88.63%); 46/54 (85.19%) |
| auto-final-offline-ppocr-v6-small-a30 | 393/435 (90.34%); 46/54 (85.19%) | 318/343 (92.71%); 46/54 (85.19%) | 311/343 (90.67%); 46/54 (85.19%) |
| auto-final-offline-ppocr-v6-tiny-a30 | 353/435 (81.15%); 46/54 (85.19%) | 299/343 (87.17%); 46/54 (85.19%) | 289/343 (84.26%); 46/54 (85.19%) |
| e1-small-phase-050 | 393/435 (90.34%); 46/54 (85.19%) | 318/343 (92.71%); 46/54 (85.19%) | 311/343 (90.67%); 46/54 (85.19%) |
| e1-small-phase-020 | 368/435 (84.60%); 46/54 (85.19%) | 307/343 (89.50%); 46/54 (85.19%) | 291/343 (84.84%); 46/54 (85.19%) |
| e1-small-phase-005 | 369/435 (84.83%); 44/54 (81.48%) | 308/343 (89.80%); 44/54 (81.48%) | 293/343 (85.42%); 44/54 (81.48%) |
| e1-small-orb-050 | 376/435 (86.44%); 41/54 (75.93%) | 311/343 (90.67%); 42/54 (77.78%) | 300/343 (87.46%); 41/54 (75.93%) |
| e2-small-box060 | 327/435 (75.17%); 44/54 (81.48%) | 287/343 (83.67%); 44/54 (81.48%) | 260/343 (75.80%); 44/54 (81.48%) |
| h3-small-fast30 | 385/435 (88.51%); 46/54 (85.19%) | 321/343 (93.59%); 46/54 (85.19%) | 305/343 (88.92%); 46/54 (85.19%) |
| v1-vision-phase005 | 337/435 (77.47%); 47/54 (87.04%) | 173/246 (70.33%); 47/54 (87.04%) | 172/246 (69.92%); 47/54 (87.04%) |
| v2-vision-fast30 | 355/435 (81.61%); 46/54 (85.19%) | 187/246 (76.02%); 46/54 (85.19%) | 187/246 (76.02%); 46/54 (85.19%) |
| linux-static-small-tune | 380/435 (87.36%); 44/54 (81.48%) | 321/343 (93.59%); 44/54 (81.48%) | 304/343 (88.63%); 44/54 (81.48%) |
| linux-cuda-medium-tune-contended | 380/435 (87.36%); 44/54 (81.48%) | 314/343 (91.55%); 44/54 (81.48%) | 304/343 (88.63%); 44/54 (81.48%) |

PP-OCRv6 Small A30 primary is **311/343 (90.67%) natural; 46/54 (85.19%) synthetic**. Its median area is **13.00%**, protection **8.19%**, and the real-video guard remains false. The retained Linux static Small primary is **304/343 (88.63%) natural; 44/54 (81.48%) synthetic**, median area **13.78%**, protection **0.62%**, real-video guard false. Neither is a gate pass or an accepted Q change.

All 14 original pooled natural and synthetic counts reproduce exactly. Independent denominators match the preceding independent-both rescore, and all-judge output leaks never increase hidden credit on any card. The rescore asserts both properties. Full cards/evidence are in `out/pr1-r1-truth-only-rescore-v2/`; the compact three-policy table is [bench/results/pr1-truth-only-rescore.json](../bench/results/pr1-truth-only-rescore.json). Earlier copies remain unchanged.

The first independent-both rescore finished **2026-10-30 04:12:18.879105 UTC**, before the cache identity change, satisfying the original ordering requirement. The corrected all-output-judge rescore reuses exactly those retained readings; it does not claim fresh cache-v2 OCR. Readings belong to runs at checkpoint `2dd52a610eb569ac51eedc84b7840fa852da96c9`; judge implementation files were byte-identical there and at reviewed commit `ec1d1f9`. Cached readings may predate the checkpoint: the original cache-miss commit is unknown. Every source card, raw evidence, truth and rescore source hash is retained in the provenance.

Reproduce the arithmetic on the retained local evidence with a new output directory:
```sh
scripts/host-lock shared models/.venv311/bin/python -B -m bench.rescore_independent \
  --retained-root .tmp/pr1-r1/retained-mac \
  --independent-both bench/results/pr1-independent-rescore.json \
  --out out/pr1-truth-only-rescore-reproduction
```

## Same-family output leak: regression and mutation proof

The regression supplies independently observed `ELM ROAD` on two input frames, with an output reading only from PP-OCR while testing a PP candidate. Primary hidden credit is **0/1**, and frame 0 is recorded as a leak.

- RED: physically switch primary outputs back to independent-only filtering. The regression fails because hidden changes from 0/1 to 1/1; exit 1.
- REVERT: restore `bench/scoring.py` byte-for-byte.
- GREEN: the same regression passes; exit 0.

Proof: `.tmp/pr1-r1/all-judge-leaks-mutation.json`, `all-judge-leaks-mutant-red.log`, and `all-judge-leaks-restored-green.log`. Both mutation proofs use `-B` and clear only their own scoring bytecode between legs. Final scoring source SHA-256: `e374228e668e50714c7f8c9aabdda23b986b9c1fa50809b5bec336ac3611981b`.

## One failing live guard: regression and mutation proof

One false LIVE-frame guard zeroes both natural and synthetic hidden credit through `score_records` and `score_observations`. The clocked case includes a protected frame between two LIVE frames; that frame cannot hide a failed LIVE guard. Physical `all` to `any` mutation fails both entry-point subtests with `AssertionError: True is not false` (exit 1); exact source restoration makes the same test green (exit 0). This proof was rerun against the final all-output-judge implementation.

Evidence: `.tmp/pr1-r1/video-guard-mutation.json`, `video-guard-mutant-red.log`, and `video-guard-restored-green.log`. An earlier quick proof repeat exposed stale mutant timestamp bytecode after source restoration; the new tests caught it in the Linux gate. That failed run remains retained. The final proofs and full gates all use restored source.

## Cache identity and fresh judging

Cache schema 2 hashes `bench/onnx_detectors.py`, existing judge/bridge/model sources, Tesseract binary version, pytesseract, ONNX Runtime and RapidOCR versions, macOS product version, and pixel shape/type. Cache tests observe real OCR call counts at the mocked external boundary: an identical environment hits; each source/version/geometry change misses. Old cache entries remain untouched and cannot match the new signature. New evidence records the complete cache identity.

The superseded Mac re-judge runner **54753** stopped before OCR began; its exit proof is `.tmp/pr1-r1/superseded-rejudge-exit-proof.log`. The replacement uses the final independent-truth/all-leak contract and frozen matching source `.tmp/pr1-r1-all-leaks-source`, runner **PID 22977**. It is untimed shared-lock work after the old sealed timed queue drains. It judges all seven tune clips, natural and synthetic, on the exact sealed Linux static Small movies, writing `out/pr1-independent-truth-all-leaks-rejudge-small/scorecard.json`. It has no fresh scorecard yet.

`bench/rejudge_retained.py` verifies all sealed artifact hashes, leaves original movies/masks/timings/evidence untouched and preserves their original processing fingerprint. Fresh OCR cannot qualify historical performance. State: `.tmp/pr1-r1/rejudge-all-leaks-runner.json`; source hashes: `.tmp/pr1-r1/rejudge-all-leaks-source.json`; OCR log: `.tmp/pr1-r1/rejudge-all-leaks-ocr.log` once started. The runner exits by Friday **09:00 PT / 16:00 UTC**. Safe cooperative stop:
```sh
scripts/mac --no-sync python3 -c 'from pathlib import Path; Path(".tmp/pr1-r1/rejudge-all-leaks-stop.json").write_text("stop\n")'
```

## Final verification

- Mac: `scripts/mac --seconds 600 scripts/host-lock shared scripts/check` **exit 0**: **105 tests (one platform skip), three relay tests**, Python compilation and optimized Swift bridge build. Receipt: `.tmp/pr1-r1/mac-full-gate-all-leaks.log`.
- Linux: one `set -e` command runs **105 tests (one platform skip), three relay tests** and Python compilation, **exit 0**, under the shared host lock, nice 10 and the agent slice. Receipt: `.tmp/pr1-r1/linux-full-gate-all-leaks.log`. The main suite uses `models/.venv311/bin/python`; relay tests use existing `.tmp/m2/linux-venv/bin/python`, which has PyAV. No new dependency was installed.
- Both physical mutations fail for their named regression, restore byte-for-byte and return green. Final scoring/judge/lane/helper code matches the frozen Mac re-judge snapshot. `git diff --check` passes.

## Historical held-out report, unchanged

The original one-shot Vision held-out result remains **47/60 pooled natural (78.33%), 22/22 synthetic (100%), median area 19.88%, 0% protection, real-video guard false, gate false**. It used the pre-correction pooled/correlated truth and is not the new primary result. The selected measurement is the last complete contended attempt (3), chosen before OCR. No attempt label, original byte, held-out grade or policy was changed. Source: Mac `out/m1-heldout-final/scorecard.json`; unmodified local copy `.tmp/pr1-r1/old-heldout-as-is.json`. Three fresh licensed held-out clips remain required before the final policy evaluation.

## Live queue and next action

Fresh Linux queue **irl-shield-builder-m2-queue-1**, central `.tmp/irl-shield-builder-m2-queue-1`, detached runner **PID 3141521**, nice 10 in `app-t3code-agents.slice`. M2 has the absolute enqueue/receipt/seal commands. The canonical `/tmp/agents/irl-shield/perf.lock`, readiness and `other_busy-v2` rules are unchanged. It exits empty-and-sealed or Friday 09:00 PT. Safe stop:
```sh
REPO_ROOT/scripts/perf-queue --queue-dir REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1 stop linux
```

Opus can commit the corrections and run review round two. Q1–Q3 Ultra worktrees still wait for that fixed head; each uses independent truth, all-judge leaks, and the real-video guard. M2/M3 continue in their original worktrees. Lock security and PerlLease replacement remain deferred until the overnight runners stop. No new GStreamer/OpenVINO work tonight.
