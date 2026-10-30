# Q giant audit ledger

Start: 2026-10-30 10:54 UTC. Stop: 12:54 UTC (two hours), earlier than 13:00 UTC.
Assigned worktree: `/home/elan/.t3/worktrees/irl-shield/t3-4fb60399`.
Base: `a8a06e30c2e5bdd8be054bbddf3c69169fe64e39`; initially clean on
`t3/q-giant-audit`, renamed `elannash/q-giant-audit` and locked for receipts.
No commits, staging, pushes, PRs, root source/cache writes, Mac work or children.

Skills read: codebase-design, tdd, diagnosing-bugs, receipt-audit;
test-review gate; research measurements section. No new dependency or license.

Budget: at most 16 test/model-probe invocations, including failures. Static
receipt reads and source inspection are not model or test invocations.
Every model job and source decode/replay uses root `scripts/q-run WT exec --`.
No corpus OCR, held-out pixels, timing/throughput qualification or all7 run.

## Invocation ledger

Pending. Commands and results are appended before/after each invocation.

1. Historical replay, natural Mazatlan; no model. Exact command:
   `/home/elan/code/irl-shield/scripts/q-run /home/elan/.t3/worktrees/irl-shield/t3-4fb60399 exec -- /home/elan/code/irl-shield/.tmp/linux-probe/.venv/bin/python -u -B -m bench.giant_audit --bundle /home/elan/code/irl-shield/out/q-base-a8a06e3-cache3-v3/mazatlan-aquiles-natural --out out/giant-audit/natural.json`.
   Pending; output log `out/giant-audit/replay-natural.log`.

Queue note (10:58 UTC): invocation1 holds root quality-linux lease and is blocked
on canonical SH by existing M2 perf job PID56963 (exclusive). No bypass, kill or
root/process change. Independent raw-receipt analysis continues.

Receipt checks: Q2 CUDA reading is pavement `11` .53872; all eight positives
retain under rejected .5 recognition. Exact earlier Tiny640 direct-source probe
is not the baseline fast-lane preprocessing (baseline resizes to640x360 first).
Historical confidence remains null. New representative inference will use exact
baseline resize/static artifacts and require exact matching historical quads.

2. Lightweight synthetic provenance executable check, no model/source decode:
   `OMP_NUM_THREADS=2 OMP_THREAD_LIMIT=2 OPENBLAS_NUM_THREADS=2 PYTHONPATH=. systemd-run --user --scope --slice=app-t3code-agents.slice nice -n 10 /home/elan/code/irl-shield/.tmp/linux-probe/.venv/bin/python -B .tmp/giant-audit/audit_contract.py`.
   Checks exact same-source lane attribution and deliberately inconsistent stored
   raster rejection through replay(). It does not prove a confirmation policy.
   Result: infrastructure failure before test: DBUS_SESSION_BUS_ADDRESS and
   XDG_RUNTIME_DIR undefined. Counted as failed invocation; no assertion ran.

3. Retry2 with the normal root-harness user-bus variables:
   `XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus OMP_NUM_THREADS=2 OMP_THREAD_LIMIT=2 OPENBLAS_NUM_THREADS=2 PYTHONPATH=. systemd-run --user --scope --slice=app-t3code-agents.slice nice -n 10 /home/elan/code/irl-shield/.tmp/linux-probe/.venv/bin/python -B .tmp/giant-audit/audit_contract.py`.
   Invocation3 result: PASS; both distinct same-source lanes preserved, exact
   synthetic replay accepted, deliberately wrong raster hash rejected. Log read.
   cv1 is explicit in the retained script for subsequent runs; the initial
   synthetic first-frame check used OpenCV defaults on64x96 pixels. No model,
   throughput or native-performance claim derives from it.

4. Affected existing synthetic contracts (motion, source-deadline engine, ideal
   offline scheduling). No models, OCR, corpus render, public listener or Mac:
   `XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus OMP_NUM_THREADS=2 OMP_THREAD_LIMIT=2 OPENBLAS_NUM_THREADS=2 PYTHONPATH=. systemd-run --user --scope --slice=app-t3code-agents.slice nice -n 10 /home/elan/code/irl-shield/.tmp/linux-probe/.venv/bin/python -B .tmp/giant-audit/affected.py`.
   OpenCV threads1 inside runner. Pending log `out/giant-audit/affected.log`.
   Result4: FAILED,24 test slots, one import error (GPU SDK lacks pytesseract
   required by existing offline test imports);23 other tests passed. This was
   not a detector/OCR failure or regression. No dependency install attempted.

5. Retry affected contracts with existing complete CPU SDK, same runner and
   limits, changing only Python to
   `/home/elan/code/irl-shield/models/.venv311/bin/python`.
   Result5: GREEN,24 existing tests passed. Log tail read. This covers motion,
   source-deadline and offline-schedule contracts with synthetic inputs. No
   production mask policy changed, and this is not the full Mac/Linux gate.

Lock diagnosis11:06 UTC: selected non-secret launch metadata for existing M2
exclusive job reports `--seconds1200`; we do not inspect or reproduce its other
arguments. Its hard-stop/run-start are scheduler metadata, not this lane's
permission. Root quality serialization and canonical SH remain in force.

Conductor steering11:12 UTC: B12 completed/rejected; no improvement in primary
counts, area worsened and Mazatlan guards remain false. This is supplied status,
not a candidate evaluation by this lane. Root a8 remains frozen. Target diagnosis
before12:30 UTC; deadline13:00 UTC and original16 invocation cap unchanged.
Prior .952727/.997831 values are quad area fractions; .598574/.508024 are
reproduced detector box scores. No historical detector confidence is invented.

6. Conservative budget accounting: the one stdlib `ast.parse` syntax check of
   bench/giant_audit.py and the three scratch Python runners is counted as a
   verification invocation too (all parsed). No imports/model/code execution.

11:17 UTC lock update: existing exclusive holder is module `relay.soak`.
Its elapsed time exceeds its requested1200 seconds; that flag does not establish
when the lease will release. Do not infer pass/fail or touch its processes.
This lane's queued invocation1 has not yet entered the replay command.

Invocation1 result11:26 UTC: FAILED exit124, root harness process-group deadline
while waiting for canonical SH. No replay command or detector inference began.
Log `replay-natural.log` says `Command exceeded its process-group deadline`.
The existing relay.soak exclusive holder PID56963 survives; it is not ours.

7. Retry invocation1 with identical command and output target, separate log
   `out/giant-audit/replay-natural-retry.log`. No partial natural.json exists.
   Existing authorization/budget/deadlines and canonical leases remain in force.

11:30 UTC source finding: fidelity requires at leasthalf unmasked raster pixels.
A .5 raw-area-only trigger cannot affect synthetic Mazatlan: zero raw giant
receipts in that whole stream, despite33 oversized LIVE unions and4 protection
masks. This identity-operation argument does not rely on box-nearness matching;
projection/padding/union attribution still awaits the actual replay.
   Invocation7 result11:35 UTC: GREEN,150/150 natural frames replay exactly;
   zero geometry/coverage/state/raster/archive/motion mismatches;82 selected.
   The canonical lease released; the existing soak process was not touched.

8. Synthetic Mazatlan replay, identical command to7 with bundle suffix
   `mazatlan-aquiles-synthetic` and output `out/giant-audit/synthetic.json`.
   Exact command below; log `out/giant-audit/replay-synthetic.log`.
   Invocation8 result: GREEN,150/150 synthetic frames replay exactly;37 selected,
   zero mismatches. Four PROTECT frames64–67 have unresolved accurate motion;
  33 oversized LIVE unions are dominated by fast-lane receipts. Maximum polygon
   area change from projection is below3.4e-16 across both variants.

9. Bounded CUDA DB support/unclip/density probe: seven representative Mazatlan
   source frames, eight hash-checked Q2 positives, five full-frame originals
   (street/store/plate/house824/house11). No corpus OCR, heldout or all7.
   Exact command:
   `/home/elan/code/irl-shield/scripts/q-run /home/elan/.t3/worktrees/irl-shield/t3-4fb60399 exec -- env PYTHONPATH=. /home/elan/code/irl-shield/.tmp/linux-probe/.venv/bin/python -u -B .tmp/giant-audit/probe.py`.
   Script retained as `out/giant-audit/probe-command.py`; log `probe.log`.
   The tap calls the actual unchanged RapidOCR postprocessor and matches by
   exact output geometry. Prior score sorting is not used as provenance.
   Invocation9 result: completed20 bounded cases (40 detector calls +20 crop
   recognitions), not a corpus grade. Twelve scheduled representative receipts
   matched raw geometry exactly; two accurate unscheduled source indices have
   no historical receipt and are labeled accordingly. All13 synthetic positives
   have source ink fully covered (1.0) by each unchanged baseline lane. These
   are baseline controls, not evidence that an unimplemented arm retains them.
   New reproduced frame45 Tiny boxscore .6005475733978568, area .95544921875;
   Small boxscore .5080196312209374, area .9978309461805556. Historical confidence
   remains null. Source PNGs (scratch) and full-frame11/store controls opened.

10. One-knob area-aware unclip cap diagnostic on the saved probability maps;
    maximum raw quad fraction .5, identical policy on both lanes, no model calls.
    Expansion is reduced only around the original pre-unclip rectangle and
    never shrinks below it. Uncappable support retains its original geometry.
    This is scratch-only and cannot enter the engine. Test all13 positives,
    including full-frame11, then reject as blocker fix regardless of retention:
    removing the entire triggered set already leaves natural45 at .528395 and
    does nothing to synthetic. Command:
    `/home/elan/code/irl-shield/scripts/q-run /home/elan/.t3/worktrees/irl-shield/t3-4fb60399 exec -- env PYTHONPATH=. /home/elan/code/irl-shield/.tmp/linux-probe/.venv/bin/python -u -B .tmp/giant-audit/cap_probe.py`.
   Invocation10 result: GREEN for13 positive source-ink retention cases on both
   lanes; candidate_accepted=false. Saved cap receipt read. Natural45 single
   capped receipt still masks .906357 fast/.905571 accurate after unchanged
   padding. More decisively, the full exact replay's unchanged smaller-receipt
   union is .528395, so no modification limited to raw>=.5 can pass that guard.
   This is a rejected scratch cap, not an optional production adapter.

Final verdict: no production confirmation/cap arm, no engine change, no all7
candidate render or grade. Candidate corpus metrics remain null. Ten budgeted
invocations, including three failed attempts (bus setup, missing optional test
import, lease timeout). No new model/download/package/license or Mac work.

11. Final synthetic audit contract rerun with explicit OpenCV1 in the retained
    runner. Same command as3, log `out/giant-audit/audit-contract-final.log`.
    No model or corpus work. This is the final verification invocation.
    Invocation11 result: PASS. Final total11/16, including3 failed attempts;
    only invocation9 called models. Retained runner now matches final cv1 run.
    Model before/after SHA256, size and mtime_ns all identical (five files).
    All foreground tool sessions exited. Final production source diff is empty;
    only three explicitly owned new files remain untracked for Opus application.
