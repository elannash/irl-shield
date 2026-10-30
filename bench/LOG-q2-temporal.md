# Q2 temporal lane ledger

Readiness PASS / evaluation HELD. Base
`65891cb0b515bc0c34ec4ded89aa6a3228992cc2`, app branch
`t3/temporal-optical-flow-tracking`, worktree
`/home/elan/.t3/worktrees/irl-shield/t3-26ca396c`.
Task: <t3-thread://v2/a3857748-9579-4ce2-b37e-5d3cd3faad44/thread:delegated-task:command%3Amcp%3A4604c41b-99c6-432d-bed9-120571e9de69%3Adelegate-task%3A22093f51-5cd1-411b-a06d-bd805ee95e07>.
Runtime readback: Codex gpt-6.1-sol, XHIGH, priority, no changes or children.

## Authority and retrieval ledger (not benchmark/test invocations)

- Verified cwd, initially clean status, assigned branch and exact HEAD before
  edits. Locked this worktree with reason "Q2 temporal lane patch and synthetic
  receipts pending coordinator apply". First lock command lacked its path and
  printed usage; corrected command succeeded. No checkout/reset/worktree creation.
- Read required codebase-design, tdd, test gate, diagnosing-bugs Source and
  hypothesis checks, research Measurements and metered calls, receipt-audit.
  Read engine/motion/worker code, value records, existing tests, check gate,
  offline/clocked/quality harness seams and routing Roles. No GLOSSARY/ADR path
  matched repository file enumeration. This is feature work, not a new historical
  detector-defect hypothesis.
- Read four historical `.tmp/q/frozen-a8a06e3` metadata files; recorded hashes
  in `out/q2-temporal/history-metadata.json`. Paths come from the actual plan;
  no nonexistent `out/frozen` path was assumed. Read giant audit Markdown,
  source identity and historical raw-giants metadata; enumerated its output
  files without decoding media or recomputing any grade. Both detector-origin
  raw geometry and temporal union issues remain historical facts, not a
  simplistic global rectangle cause.
- Focused rg attempts named absent pyproject/Makefile/offline_pipeline and
  `.github` paths and returned ordinary missing-path errors; subsequent reads
  used actual file paths. These were retrieval failures, not execution runs.
- Read exact SDK symlink metadata without resolving/replacing its interpreter.
  Used only `/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python`
  for CPU test invocations. No venv installs, overlays or external calls.
- No PHONE_TEST_DONE/GPU_RELEASED or V2_FROZEN SHA was supplied. No GPU status
  polling, queue submission, runner, Mac contact, video render, OCR, scene screen,
  benchmark or heldout eval took place. New v2 fixture content/manifest was
  neither edited nor inspected. No baseline/historical result was overwritten.

## Counted invocations

All paths below are under `out/q2-temporal/`. Exact commands are retained in
`commands.json` and helper copies. Each top-level test/helper invocation counts
once, including failures; mutation helper's one child unittest run counts as
that same single test execution, not an extra benchmark. The bounded fixture
search counts once; its cases are CPU synthetic inputs inside that unit test.

| # | Receipt | Actual result |
| ---: | --- | --- |
| 1 | `01-flow-red.log` | 7 tests, one expected unsupported-interface error before feature |
| 2 | `02-flow-green.log` | 7 tests PASS, shear/translation and baseline geometry |
| 3 | `03-fences-red.log` | 8 tests, one expected behavioral failure: out-of-horizon projection accepted |
| 4 | `04-fences-green.log` | 8 tests PASS, horizon/generation history fences |
| 5 | `05-engine-red.log` | 12 tests, one expected unsupported generation-submit interface error |
| 6 | `06-engine-green.log` | 12 tests PASS, worker generation relay and fail-closed engine recovery |
| 7 | `07-contracts.log` | 25 tests, one incorrect test expectation; target frame's own fresh receipt correctly kept LIVE. Corrected test to assert exclusion of old quads, with no production change. |
| 8 | `08-fb-fixture.log` | 1 synthetic unit test PASS; bounded 20-case fixture search finds backward-error-only mutation witness at translation40 / erased256. No real video/quality screen. |
| 9 | `09-guards-red.log`, `09-mutation.diff`, `09-restoration.json` | 6 tests with 5 deliberate behavioral failures; removed no-fallback, generation, history horizon, backward error and engine horizon guards, restored source byte-for-byte. Harness wrapper exit0 means expected unittest exit1, not green tests. |
| 10 | `10-final-green.log`, `10-tests.json` | 28 tests PASS, 0 skips; real synthetic flow/engine/worker and reference engine, policy derivation/compile checks, OpenCV1 |
| 11 | `11-package-check.log` | Metadata/patch contract validation, reverse apply check, syntax/JSON checks and owned-path fence; no media/GPU/model work |

Count at hand-back: **11/20 used, 9 reserved/unspent**. GPU/quality/performance
invocations: zero. Retrieval and package-writing commands above are separate;
#11 conservatively counts the package validation as an invocation. No future
all7/render/grade/profile execution is charged or authorized by this ledger.
Root must reconcile its shared aggregate budget before any expanded plan runs.

CPU prefix used for #1–10:

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
OPENCV_FOR_THREADS_NUM=1 PYTHONDONTWRITEBYTECODE=1 \
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B ...
```

#1–4 use `-m unittest discover -s tests -p test_motion.py`; #5–6 use
`-m unittest discover -s tests -p test_deadline_engine.py`. #7 loads motion,
deadline engine and motion worker via unittest's loader with repo/tests path.
#8–10 use `.tmp/q2-temporal/{guard_fixture,mutate_guards,final_cpu}.py`.
Exact -c program for #7 and all helper bytes are retained with the logs.

Final proof: public MotionHistory projection and actual MaskingEngine submit /
poll exercise finite vertex-preserving shear transforms, inverse mapping,
generation disconnection even on identical pixels, empty receipts, failed
motion/gaps/low texture, projection horizon and worker deadline contracts.
The cut/phase-fallback, generation and horizon guards have physical behavioral
red receipts; a separate single-guard synthetic experiment checks the backward
error. No claim of real-world hiding or GPU time follows from these tests.

Full `scripts/check`: NOT RUN, because discovery performs encoded video /
quality-bundle / heldout harness rendering forbidden in this readiness phase.
No credential/service was needed by the focused tests. No Mac native build ran.

## Hand-back and retained files

`bench/q2_temporal/README.md` owns architecture, one-knob policies, semantic
coupling of A/D, exact outside-fence seam blockers and the unexecuted quality /
performance plan. `execution-plan.json` supplies literal argv and receipt paths.
No D>1 adoption, screen result, guardpass, near miss or winner is reported.
The GPU cost argv is explicitly unavailable until root supplies real device
instrumentation; host service timing cannot satisfy it.

`.tmp/q2-temporal/implementation.patch` includes only four tracked engine/motion
source/test files plus this lane's new bench subtree and lane log. All intended
post-application file hashes and base blobs are in `.tmp/q2-temporal/handback.json`.
New bench files are intentionally untracked, not falsely reported as git-tracked.
No ignored secrets are force-added. No staging/commit/push/PR action occurred.
All owned subprocesses have exited; no background service or Mac process was
started, and tests close owned motion threads. Worktree stays locked for root.
