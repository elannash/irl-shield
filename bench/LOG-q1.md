# Q1 edge-clamp audit ledger

- 2026-10-30 04:47 UTC: verified isolated worktree, clean tree and exact base
  `0648e0f64d599b223d101f6643ed7d75a36331e3`; renamed prepared branch
  `t3/q1-edge-clamp` to `elannash/q1-edge-clamp`. Timebox started at the initial
  task, no later than 04:47 UTC; six-hour deadline no later than 10:47 UTC.
- Loaded packet-required codebase-design, TDD, test gate, diagnosing-bugs,
  research Measurements, receipt-audit and machine Shell traps. No children.
- Read corrected primary scoring contract and retained rescore. Limited reads
  to tune evidence. Located the exact historical 15-interval taxonomy at
  `/tmp/agents/irl-shield/m1-async-taxonomy/report/taxonomy.json` and its original
  source artifacts in root `out/offline-vision-union-a30/`.
- Copied only the PP E1 Mazatlán synthetic input/output, masks, cached detections,
  motion/engine metadata, and evidence into lane `.tmp/q1/e1-small-phase-005/`.
  Copies are read-only inputs to the audit; originals were not modified. No
  dependencies were installed. The Mac source input SHA-256 was checked before
  copying: `991cd0f092ff1ffeca5f7f24041ec674052530abff3cb572e8e642c6c9d1c222`.
- Added lane-owned diagnostics. Seven literal boundary cases pass. Deliberate
  physical edge-drop mutation goes red on the expected visible-pixel assertion;
  exact renderer restoration returns green. No real production bug reproduced.
- Audited 45 unique historical frame rows plus PP frames 78/79/148/149. All 49
  saved masks reproduce exactly. Of 206 offscreen-quad occurrences, 128 have
  visible original pixels; none loses any original visible pixel. The four
  synthetic targets have zero original-quad and zero padded-mask overlap.
- Replayed all seven historical variants containing the 15 intervals: 1,050
  frames, 520 target-frame projection calls, 81 unresolved whole receipts, zero
  partial drops. Separate PP replay: 150 frames, 36 calls, five unresolved, zero
  partial drops. Linux/Mac replay is not bit-identical; counts are diagnostics,
  not fresh quality or performance acceptance. Literal per-variant commands and
  return codes: `.tmp/q1/projection-replay-launches.json`.
- Inspected actual input/encoded-output/mask crops for all four synthetic frames:
  `/tmp/agents/irl-shield/q1-edge-clamp/cedar-edge-frames.png`. They visibly retain
  CEDAR AVE. Benchmark-only, not demo-ready.
- Affected tests: `python -B -m unittest tests/test_motion.py tests/test_render.py -v`
  using root `models/.venv311/bin/python`, nice 10, native two/OpenCV one, agent
  slice, canonical shared lease: ten pass. Full Linux functional run: 105 main
  tests (one skip), three relay tests, compileall; all exit zero in one run.
  `.tmp/q1/affected-motion-render.log`, `.tmp/q1/linux-functional-gate.{json,log}`.
  Swift bridge build remains unverified on Linux. No test-suite files changed.
- Root supplied `scripts/q-run` and `bench/quality_bundle.py`; read them in place.
  Ran the final geometry diagnostic through pinned root GPU SDK under the
  serialized quality/shared perf leases. It reproduces all audit counts and
  seven boundary checks. `.tmp/q1/pinned-edge-audit.log` and
  `out/q1/retained-edge-audit-pinned.json`. No GPU inference or Mac OCR launched.
- Decision: Q1 falsified in the requested evidence. Reject edge clamp; leave
  motion/render/coverage untouched. Root common refreshed baseline is pending
  pilot approval. Historical seven-clip primary cards are context only, both
  fail real-video and per-clip protection guards. No numeric Q1 delta exists.
- Root announced merge `631dc5b` with unchanged `0648e0f` content and five pending
  P2 benchmark corrections. Q1 passes no family override; registry provenance
  remains authoritative. No Mac OCR or final Q score acceptance before root's
  fixed-head/harness notice. The existing tests are explicitly pre-follow-up
  evidence; root owns rebase. Owned work remains uncommitted.
- Hand-back prepared with no production or test-suite edits, no retained jobs,
  and all source deliverables unstaged. Budget used: three unittest invocations,
  two deliberate mutation checks, four geometry checks (including reruns), nine
  cached projection replays: 18/24 conservatively counted engine verification
  invocations. Geometry diagnosis is complete; fresh quality acceptance stays
  held for the root P2 follow-up and common baseline.

The separate PP projection replay used:

```sh
XDG_RUNTIME_DIR=/run/user/1000 \
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
systemd-run --user --scope --slice=app-t3code-agents.slice nice -n 10 \
scripts/host-lock shared \
/home/elan/code/irl-shield/models/.venv311/bin/python -B \
  -m bench.q1_projection_replay \
  --prefix .tmp/q1/e1-small-phase-005/mazatlan-aquiles-synthetic-masked \
  --source .tmp/q1/e1-small-phase-005/mazatlan-aquiles-synthetic-input.mp4 \
  --card /home/elan/code/irl-shield/out/e1-small-phase-005/scorecard.json \
  --targets 78,79,148,149 --out out/q1/pp-mazatlan-projection-replay.json
```
