# Queue execution retry accounting

START readiness rejections previously consumed the three-attempt budget because
`Queue.begin` appended a trial before START and both budget checks counted the
length of that list. A job could exhaust without executing its command. The
queue now charges executions and keeps pre-execution rejections separately.
This change affects orchestration only; it adds no dependency, model, data,
media, service or license. Existing assets remain benchmark-only, without
music, and are not demo-ready.

## Persisted state and definitions

The interface remains `Queue.begin`, `Queue.finish`, `Queue.recover`, status and
`Runner`; no scheduler or migration command is added. Existing metadata flocks,
atomic JSON replacement, readiness/contamination thresholds, priority ordering,
canonical performance lease and foreground watchdog remain in use.

- `job.attempts` lists execution receipts and the currently claimed trial. Old
  entries remain in this list, including historical pre-execution rejections.
  Its length is no longer the execution count.
- `job.preexec_rejections` lists new closed trials that did not execute. It is
  optional on old jobs and is created when needed. Receipt paths stay in their
  original `attempts/NNN/attempt.json` directories; no file is moved.
- `attempt` is the unique one-based **trial ordinal**, shared by its directory,
  `{attempt}`, and `IRL_SHIELD_PERF_QUEUE_ATTEMPT`. It can exceed three.
- `execution_started` is false during the new starting/prepared phases. The
  runner durably marks it true immediately before launching the foreground
  watchdog. A normally closed receipt records whether the watchdog was spawned.
- `execution_attempt` is the logical one-based execution number (one to three)
  when launch begins, and null for a new closed pre-execution rejection. It is
  diagnostic metadata, not the name of an artifact or an alternative budget.
  Legacy recovery cannot always reconstruct this field and may leave it null.

A receipt with `rejected_before_exec: true` never consumes the execution budget.
An explicit `execution_started: false` also excludes it. All other receipts,
including absent legacy receipt files and legacy trials with no execution flag,
consume budget conservatively. Invalid JSON still raises; it is not silently
accepted as proof of non-execution.

A failed executable, nonzero command, killed command or crash after launch
commitment consumes an execution. An uncontended nonzero command remains
`failed`, rather than receiving a contention retry. A new runner crash known to
precede launch is logged separately. Child or command-exit evidence overrides
an old false execution flag during incomplete-trial recovery. The small crash
window between persisting launch commitment and spawning is ambiguous and
therefore charged; this can conservatively spend budget without a proven
command start, but cannot grant an unbounded retry to a crashed execution.

## State transitions and compatibility

| Event | Result |
| --- | --- |
| START rejected or control stops before launch | Receipt retained, trial separated, job pending; execution budget unchanged |
| Contended execution, fewer than three executions | Job pending at back of its priority |
| Third contended execution | `exhausted-contended` |
| Clean exit zero / clean nonzero | `completed` / `failed` |
| Legacy exhausted job with explicit pre-execution rejections and fewer than three executions | Recovery returns it to pending without rewriting old receipts |
| Completed/failed legacy job | Terminal state preserved |
| Live orphan watchdog | Existing identity-based wait/ACK behavior |
| Incomplete trial with ambiguous or positive launch evidence | Retained as contended; execution charged |

Recovery's known-path set includes both lists. It does not rediscover a
separately logged rejection as an orphan execution. It also recovers a closed
rejection left between the receipt write and the job metadata update, without
rewriting the closed receipt. Repeated recovery is stable. Allocation uses the
maximum numeric directory already on disk plus one, including reservations
without a receipt after a crash. It never reuses a directory after removing a
trial from the execution list.

For example, four rejected START trials followed by the first execution create
trial directories 001 through 005. The command receives `{attempt}=5` and writes
`output-5`, while its `execution_attempt` is 1. A legacy history containing
rejected trial 1, executed trial 2 and rejected trial 3 has two executions left;
new trials 4 and 5 can spend those, without overwriting `output-1` through
`output-3` or changing their labels. Custom command output names must still use
the ordinal placeholder or another unique path; the queue cannot protect a
command that explicitly writes the same fixed filename every time.

Closed legacy receipts and their health, labels, stdout/stderr and artifact
bytes are not relabelled or rewritten. Migration changes only job metadata
under its existing queue lock. It does not reset executed history or create a
new qualification job. Mixed old/new history is supported by this version.
Downgrading to an older runner after new rejection metadata exists is unsafe:
that runner would rediscover the separate trials and count every trial again.
Do not run mixed runner versions against a queue.

The joined report needs no change: old rejected receipts remain available in
history, new rejection paths are visible in its queue status, and only actual
closed attempts with benchmark artifacts produce report rows. Neither queue
completion nor the functional tests establish a performance or privacy pass.

## Verification and hand-off

`tests/test_preexec_retries.py` imports the existing fixture **module** and uses
its setup and runner helpers without subclassing or exporting its TestCases;
unittest discovery runs the existing tests once. Synthetic health and real
files/minimal foreground commands exercise the public queue seam. No test
requires a performance host, GPU, Mac job, model download or actual live queue.
The tests cover the exact rejected-START regression, four rejections before the
first execution, three real contended executions, legacy mixed history with
byte preservation, distinct output placeholders and crash recovery at metadata
write boundaries. Existing queue tests cover failed commands, orphan watchdogs,
lease ownership and stop/deadline behavior.

The original red run, green runs, mutation evidence, complete Linux functional
run and source hashes are recorded in `out/queue-retries/handback.json` and its
referenced logs. The Linux run covered both test directories and compilation;
the top-level suite had three judge-cache import errors because the initial
environment lacked `onnxruntime`. Those three tests subsequently passed using
the existing model environment's packages read-only. This is not a green full
gate; the parent must run its gate in a complete environment. The macOS-only
VideoToolbox test was skipped, and the Swift bridge build was not run on Linux.
The immutable patch is `out/queue-retries/changes.patch`;
`post-apply-sha256.json` gives the expected file hashes after integration. The
new regression fails against the original queue because a rejected START
remains in `attempts`, despite no command launch or samples.

## Parent activation procedure (not performed by this child)

1. Review/apply the patch independently of the first P2Q change and verify its
   SHA-256 and the post-apply file manifest. Review the two new files as well as
   tracked diffs. The child does not stage, commit, push or create a PR.
2. Run the parent gate and cross-vendor review. `tests/test_perf_queue.py` is
   parent-owned and unchanged by this patch. Integrate the parent's deterministic
   fixture correction separately; do not weaken production contention policy
   to accommodate its short busy-file timing window.
3. Arrange the cutover at a job boundary. Do not restart or replace code used by
   a runner/watchdog mid-job. A cooperative stop during a job interrupts it;
   the parent must first establish an idle boundary and serialize the cutover
   using its existing runner ownership procedure. Confirm the old runner and
   its watchdog have exited and the performance lease has been released before
   replacing source or starting the new version. Preserve all queue/artifact
   directories and metadata; do not clear locks or reset attempts.
4. Start one runner per host with the reviewed source and existing bounded
   environment. Startup recovery reconciles eligible legacy exhausted jobs and
   closed receipts. Inspect status and receipt paths; an eligible old rejection
   must not spend budget and a completed execution must still do so. Do not run
   an older version concurrently or downgrade it against the changed metadata.

This hand-off authorizes no activation. The parent owns gates, review, commits
and job-boundary activation. No actual queue, queued job, runner, existing
process, account, secret, host setting, benchmark asset or performance policy
was changed by this implementation child.
