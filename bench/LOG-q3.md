# Q3 persistence ledger

- 2026-10-30 04:47:21 UTC: task starts, six-hour deadline 10:47:21 UTC.
  First commands verify cwd, prepared branch, exact base and clean tree.
  Renamed branch in place from `t3/q3-persistence` to `elannash/q3-persistence`.
- Read requested skills, worktree governance, PR1 truth-only rescore and
  `docs/PR1-R1-FIXES.md`. The historical real-clock and Core ML cards are
  diagnostic context only. No held-out artifact read.
- Read existing engine/motion/offline code. B already controls older-receipt
  selection and retention; coverage validity remains separate. No engine fix
  identified, so no production or unit-test change is warranted.
- Read historical primary offline e1 tune evidence. Read-only Mac tar copies
  only `out/e1-small-phase-005/*detections.json` and `*motion.json` into lane
  `.tmp/q3/`; no GPU render or OCR launched. Pure-JSON diagnostic probe writes
  `out/q3/historical-{gaps,persistence-opportunities}.json`.
- Verification invocation 1/24: literal synthetic-pixel persistence probe,
  `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
  nice -n 10 /home/elan/code/irl-shield/models/.venv311/bin/python -B
  .tmp/q3/persistence_probe.py > out/q3/literal-persistence-probe.json`.
  Exit 0, read result: B12 retains geometry after B6 expiration; B24 does not
  relax stale/error/deadline/disconnection constraints. No red/green claimed.
- Heavy work remains held for root's common Linux CUDA/Mac OCR harness.
  No new dependency, model, SDK, dataset, install, account, service or license.
- Root supplies `scripts/q-run` / `bench/quality_bundle.py`, shared
  `.tmp/q/inputs.json` (exact 14 sealed tune inputs and truth) and
  `.tmp/q/base-policy.json`. Read these files without copying/editing helpers.
  Prepared `out/q3/b12-policy.json`: the only changed option is before 6 -> 12.
  Copied existing model caches into owned Linux and Mac mirrors with rsync -aL;
  copied the existing Mac Vision bridge. No install or model download.
  Heavy remains held pending root's baseline pilot and queue-priority message.
- Root steering: PR1 merged at main `631dc5b` (same content as `0648e0f`).
  Five P2 benchmark fixes must land before Q acceptance. Do not pass a
  detector_families override; Q3 policy confirmed to omit it and still differ
  only in B. Mac OCR/final score acceptance held pending fixed-source notice.
  Original six-hour clock remains unchanged; owned files preserved.
- Verification invocation 2/24: extend the scratch literal-frame probe with
  2-pixel/frame translated texture and observe the independently expected
  translated mask center. Same public engine seam and real phase motion;
  B12 paints the translated center through frame12 and expires13, B6 expires7.
  All prior stale/late/failed/disconnected checks also pass. Exit0; read
  `out/q3/literal-persistence-probe-translated.json`. No production/test edit.
- Explicit root authorization: `git merge --ff-only
  efd513fe079c14ab4af4d9f0f9c1fcc78b855c96` advances dedicated Q3 branch to
  P2 commit. Verified actual branch elannash/q3-persistence, exact HEAD and
  both owned untracked docs preserved. Policy still differs only before6->12;
  no detector-family override. Engine/motion/render hashes unchanged.
  PR3 review/merge and frozen baseline launch remain pending; heavy/Q
  acceptance held. Deadline10:47:21Z and verification count2/24 unchanged.
- Root steering: PR3 merged main62b536f. Two retained-scoring followups remain
  required before cache3 cards: use the recorded fast lane during rescoring,
  and report dynamic cache schema scope. Root fixes these test-first and
  refreshes shared freeze. Heavy runs/grading remain held for the exact
  fixed-source baseline/harness notice. Q3 stays at efd513f pending further
  base instruction, with B12 one-knob config unchanged. Deadline and2/24
  verification count remain unchanged.
- Explicit root authorization: fast-forwarded from efd513f to full commit
  `f2f57892b731949d17ce62ba4dcd84d74fb26ab0` with `git merge --ff-only`.
  Branch elannash/q3-persistence confirmed; both owned untracked documents
  preserved; no additional worktree diff. B12 config still has sole option
  delta before6->12 and no detector-family override. No tests invoked.
  PR4 is open/reviewing; remain idle with no GPU/Mac OCR/tests until root's
  merge/frozen-manifest/exact-launch notice. Deadline10:47:21Z remains.
