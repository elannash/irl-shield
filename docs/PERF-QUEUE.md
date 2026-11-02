# Per-host performance queue

This is a one-off overnight queue, not a general service or a T3 task poller.
Root and lanes enqueue real foreground commands, finish producer submissions,
then root launches one runner on each host. The runner uses Python 3.9+ standard
library modules and installed Perl; it introduces no SDK, package, model,
dataset, media or service dependency. Existing benchmark/model/fixture license
receipts stay with each command. Footage remains benchmark-only, without music
or audio, and branded frames are not demo-ready assets. Nothing here connects
to Twitch, reads secrets, publishes, installs packages or changes host settings.

## Storage and CLI

Every lane calls the **absolute script in the root checkout**. Storage defaults
to that script checkout's `.tmp/perf-queue`, regardless of the caller's cwd.
The original caller cwd is captured before execution; the script never changes
it to the script root. `--cwd` overrides it explicitly. All argv elements after
the first literal `--` are passed without shell evaluation. Options may follow
the job name before that separator.

Set `perf_root` to the absolute central checkout path. The example assumes
`$HOME/code/irl-shield`; use that shared checkout even when your current
directory is a lane worktree.

```bash
perf_root="$HOME/code/irl-shield"
"$perf_root/scripts/perf-queue" enqueue linux root-cuda-static \
  --lane root --priority 1 --cwd "$perf_root" \
  --receipt '{job_dir}/output-{attempt}.performance.json' -- \
  "$perf_root/.tmp/linux-probe/.venv/bin/python" -m bench.clocked_pipeline \
  --candidate ppocr-v6-medium --provider cuda --fast-provider cuda \
  --static-model --encoder h264_nvenc \
  --output '{job_dir}/output-{attempt}.mp4'

"$perf_root/scripts/perf-queue" status
"$perf_root/scripts/perf-queue" status linux
```

The example shows queue transport; root retains responsibility for all selected
benchmark flags and the existing private CUDA library environment. Enqueue
direct underlying benchmark commands. **Do not enqueue `scripts/linux-bench`,
`scripts/host-lock`, or another command that reacquires the same performance
lock.** Root's wrapper integration may instead verify the inherited queue lease
and explicitly skip a nested acquisition.

`{attempt}` expands to the unique one-based trial ordinal, which can exceed
three after pre-execution rejections, and `{job_dir}` to the job's unique absolute
directory. Only those literal placeholders are replaced, so ordinary braces in
Python/JSON arguments are preserved. Use them in immutable benchmark outputs
and receipt paths. Repeated `--receipt` options are supported. Relative receipt
paths resolve against the captured job cwd. Each attempt records existence,
size and SHA-256 for regular receipt files; it never invents a benchmark result.

Root defaults to priority 1; any other lane defaults to priority 2. Smaller
integers run first, with FIFO order within a priority. Priority can be explicit.
Atomic JSON replacement and a short metadata flock protect concurrent enqueue,
claim and completion operations. Status and enqueue never take the long
performance lease. The optional global `--queue-dir DIR` is for controlled
storage relocation or synthetic fixtures; all production callers on a machine
must agree on the same central directory.

Host labels do not route over SSH. `run mac` refuses to execute on Linux, and
vice versa. Enqueue Mac jobs on the Mac using its absolute root script, with
the Mac lane's own cwd, for example:

```bash
ssh mac 'bash -lc '\''cd ~/code/irl-shield && "$HOME/code/irl-shield/scripts/perf-queue" status mac'\'''
```

Use that same remote form for enqueue/seal/run; Linux and Mac each keep their
own local queue and canonical local lock. A Linux `status` does not query Mac.

## Producer seal and launch

An unsealed queue waits when empty, so a runner cannot exit before future lane
submissions. Root should enqueue all planned root/lane timing jobs, then seal:

```bash
"$perf_root/scripts/perf-queue" seal linux
nohup nice -n 10 "$perf_root/scripts/perf-queue" run linux \
  > "$perf_root/.tmp/perf-queue-linux-runner.log" 2>&1 < /dev/null &
"$perf_root/scripts/perf-queue" status linux
```

Root starts the real runner; these commands were not executed during development.
On Linux, root should place the runner in `app-t3code-agents.slice` using its
normal user-scope launcher; its foreground jobs inherit the scope and nice
level. Supply the existing benchmark environment, including two-thread native
limits and private GPU library paths, at launch or explicitly through literal
`env NAME=value ...` job argv. Mac uses the equivalent local `nohup` launch.

Sealing rejects late enqueues. `open HOST` reopens producer submission without
deleting any job or attempt. A sealed runner exits after all jobs reach a
terminal state; an unsealed empty runner waits until sealed or stopped. It does
not delegate work or discover jobs from another scheduler.

## Readiness and trust

The queue runs whenever the host is quiet overnight; there is no fixed 6:55 or
7:30 start window. Readiness starts every 120 seconds while waiting. Mac runs
exactly `top -l 2 -s 10 -n 0`, using idle from the **second** CPU sample. It also
requires successful `memory_pressure -Q`, `sysctl
kern.memorystatus_vm_pressure_level` with dispatch value 1, and records `sysctl
vm.swapusage`. A high free-memory percentage never substitutes for the normal
dispatch flag.

Linux reads aggregate `/proc/stat` twice ten seconds apart. Its total uses only
the first eight counters: user, nice, system, idle, iowait, irq, softirq, steal.
Guest counters are excluded because they are already included in user/nice.
Only idle ticks count as idle; iowait is treated as busy. `free -b` must report
at least 4 GiB available. Load, swap bytes and PSI files are diagnostics. Missing
or malformed required readings cannot produce a ready result.

A job starts only at idle >=80% and memory OK, except at the forced deadline.
The runner first takes `perf-runner.lock` beside the canonical performance
lock, then its queue-local singleton lock. A second runner using another
queue directory on the same host is rejected before readiness sampling.
It checks readiness, then
takes the exclusive canonical `/tmp/agents/irl-shield/perf.lock` and samples
START again. Perl acquires BSD flock on a descriptor retained by the runner
and foreground watchdog. This interoperates with `scripts/host-lock` across
worktrees. Never unlink a lock file to clear a stale lock; kernel ownership
ends when its descriptors close.

On Linux, `scripts/host-lock shared` temporarily takes the exclusive lease
and prints one warning to stderr. Existing argv therefore serializes with
exclusive queue jobs and merge gates. Mac shared behavior is unchanged.
Quality-bundle clip leases are exclusive on both hosts. This shim is removed
when jobs move to the aggregate slots provided by `~/.agents/bin/heavy`.

Tests inject a temporary `clip_lease(..., lock_root=...)`; they never acquire
the canonical performance lease. The unified gate rejects attempts by tests
to resolve, inspect, open or flock the global lock, or launch the production
host-lock wrapper. This catches a nested lease before it can deadlock a gate
that already owns the host lease. Queue tests also use private performance
and runner lock files.

During each job, ten-second CPU sampling windows continue without an extra
ten-second delay. START, END and periodic raw health are retained. New attempts
use `contamination_policy: other-busy-v2`; historical receipts keep their
original idle policy, labels and bytes. Readiness and the repeated START check
remain idle >=80% plus memory OK. END is outside the job, so a numeric END idle
below 60% does not itself contaminate a new attempt. Missing END health or
memory not OK still rejects trust. A rejected START is retained separately and
does not consume an execution. Historical rejected START receipts also do not
consume the execution budget; their original labels and bytes remain intact.

For each measurement window, `total_busy_percent = 100 - idle_percent` and
`job_tree_busy_percent` is identity-bound foreground job CPU divided by that
window's logical-CPU capacity. `other_busy_percent` is
`max(0, total_busy_percent - job_tree_busy_percent)`. Contamination occurs when
the interval-duration-weighted mean other busy is **above 20%**, any sample is
**above 40%**, or required health/accounting is unavailable or memory not OK.
The threshold reason is `other_busy`; unavailable CPU accounting and memory
have distinct reasons. A job using 50% while total busy is 50% has zero other
busy. At total 87.5% and job 50%, other busy is 37.5% and fails the mean rule.
Zero job CPU at total 25% also fails the mean rule: it is not equivalent to the
legacy single-window idle <60% rule.

Linux samples `/proc/<pid>/stat` own utime/stime and waited cutime/cstime for
the active watchdog and all proven descendants, including children that use
separate sessions. Membership requires a complete PPID chain to the watchdog;
process groups, sessions and birth within the sampling window never establish
ownership. Each Linux parent must have started no later than its child, and
ancestor PID/start identities and parent links are cross-checked at the
endpoints. An unrelated process or reparented orphan whose chain does not reach
the watchdog receives no credit. Summed own+waited CPU over the live tree at both
endpoints transfers a departed child's previously counted CPU into its parent's waited
counters without counting it twice. Parent links and PID/starttime identities
bind ownership; sibling processes are never credited. Reuse, missing ancestry,
or a reaping/identity transition detected inside the non-atomic `/proc` scan
invalidates accounting instead of guessing. Scan durations and per-process
endpoint counters remain in provenance.

Mac uses read-only `ps -A -o pid=,ppid=,pgid=,time=,lstart=` endpoint snapshots.
Only descendants with stable identities and parent chains at both endpoints
receive CPU credit, including separate-session children.
New, departed, reaped or reused children are conservatively unassigned, so their
CPU remains other load. This is a lower bound, including `ps` start-time and
CPU-time precision limits. OS daemon work outside the foreground ancestry is
also unassigned on both platforms. Endpoint enumeration is not atomic; its
duration is visible rather than hidden in a whole-job CPU average.

For during-job global CPU, Mac uses stdlib `ctypes` with installed libSystem
`host_statistics(mach_host_self(), HOST_CPU_LOAD_INFO=3)`. The verified SDK ABI
returns four unsigned32 ticks: user, system, idle, nice; success is code 0 and
count 4. Delta arithmetic handles unsigned wrap and uses idle index 2 over all
four deltas. The host port is cached per sensor. Raw tick vectors, interval and
API/SDK source remain in the sample. This existing OS API introduces no package
or downloaded framework. `top` remains exact and unchanged for readiness,
START and END; it is not interrupted to measure a partial job window.

The watchdog writes `command-exit.json` and keeps its root counters/lease alive
until the runner cancels and closes the final partial window, then writes
`sampling-complete.json`. Late external load is therefore not discarded with
monitor cancellation. Both hosts can retain finite global CPU for a partial
window using kernel counters alongside process-tree counters. Stop, crash,
timeout or missing-root windows fail
closed. A replacement runner can ACK an abandoned, already-finished watchdog;
it still marks the recovered attempt incomplete/contended.

Contended executions go to the back **within the same priority**, with two
retries and three total executions across policy versions; upgrading does not
reset executed history. Pre-execution rejections do not spend that budget.
See [execution retry accounting](QUEUE-EXECUTION-RETRIES.md) for state fields,
legacy recovery, unique artifact ordinals and the job-boundary cutover procedure.
A new qualification trial must be an explicitly named new job linked by root to
its history. All prior stdout, stderr, health and artifact receipts
remain in distinct attempt directories. An uncontended nonzero command is
recorded failed rather than retried as if it were contention. Exit zero yields
`completed`, meaning only process completion; every attempt keeps
`benchmark_verdict: unassessed`. Artifacts define benchmark success. The actual
command exit code is used when its watchdog recorded it; otherwise `returncode`
is the watchdog result, with `wrapper_returncode` separately retained.

## Forced deadline, hard stop and child context

On Friday October 30, 2026 at **15:00 UTC / 08:00 PT**, pending jobs run even
without readiness and are explicitly CONTENDED. They still have a maximum of
three executions. At **16:00 UTC / 09:00 PT**, the runner stops and kills only its
current owned job process group. Enforcement begins 0.1 seconds before that
boundary to leave shutdown margin; this is ordinary OS scheduling, not a
real-time guarantee. Pending work remains visible. The deadline supersedes
earlier proposed overnight windows.

Each actual child inherits these scoped values, also recorded in its receipt:

| Variable | Value |
| --- | --- |
| `IRL_SHIELD_PERF_QUEUE_FORCED` | `1` at the forced deadline, otherwise `0` |
| `IRL_SHIELD_PERF_QUEUE_ATTEMPT` | Unique one-based trial ordinal, possibly above three |
| `IRL_SHIELD_PERF_QUEUE_RECEIPT` | Absolute attempt JSON path |
| `IRL_SHIELD_PERF_QUEUE_LEASE_FD` | Inherited canonical lock descriptor |

The underlying benchmark must honor FORCED=1 by marking its own run contended
and allowing diagnostic execution, never granting a gate pass. That benchmark
integration is owned by root, independently of this queue. The worker verifies
that its inherited descriptor identifies the selected lock inode; root wrappers
can additionally compare it with the canonical path and attempt metadata before
skipping a nested lock.

## Stop, crash recovery and receipts

```bash
"$perf_root/scripts/perf-queue" stop linux
"$perf_root/scripts/perf-queue" status linux
```

Stop writes a timestamped cooperative request, not a signal to a stored runner
PID. It therefore cannot kill a reused runner PID or an unrelated process.
The runner cancels its health helper, terminates its currently owned process
group, and retains the interrupted attempt. Status records the runner PID,
start identity, identity match, state and safe stop command. Verify its stopped
state and final attempt receipt after requesting stop. A later explicit runner
start ignores an older stop request.

Every job has a foreground watchdog in a new process group; commands must stay
foreground and must not daemonize or escape that group. The watchdog retains
the performance lease and enforces the hard deadline even if the runner dies.
A replacement runner waits for a still-live, identity-matching orphan attempt.
It never signals a process found only in stale metadata. Once that process is
gone, an interrupted attempt is preserved as contended, missing END health
stays explicitly unavailable, and retry accounting continues without reset.

Per host, `runner.json`, `readiness.json`, readiness history and `jobs/*/job.json`
show state. Jobs list execution/current-trial paths in `attempts` and new
non-executed trial paths in `preexec_rejections`; legacy rejected paths may remain
in `attempts`, so list length is not an execution count. New receipts include
`execution_started` and `execution_attempt` (null if not launched). Per trial,
inspect `attempt.json`, `start-health.json`,
`periodic-health.json`, `end-health.json`, `stdout.log`, `stderr.log`, `launch.json`
and available child/exit identity files. Job status lists the immutable attempt
receipt paths and requested artifact templates. No credentials belong in argv
or logs; no environment dump is recorded, only the four queue values above.

Development verification used synthetic health and real short subprocesses,
files, concurrent enqueues and Perl/Python descriptor ownership. Live Mac health
sampling, real benchmark integration and detached overnight deployment remain
root's next steps. No persistent runner or hardware measurement was launched.

## Joined benchmark report

After attempts complete, root's reporter joins the queue attempt with its raw
benchmark receipt and verifies the retained artifact hashes and sizes:

```bash
.venv/bin/python -m bench.perf_queue_report --host mac \
  --out out/perf-queue-scorecard.json
.tmp/linux-probe/.venv/bin/python -m bench.perf_queue_report --host linux \
  --out out/perf-queue-scorecard.json
```

It emits a one-screen table and the requested JSON. Accepted timing requires
both a clean queue attempt and a hash-verified raw benchmark whose own endpoint
trust checks pass. Normal endpoint memory alone cannot erase queue contention;
measured numbers remain visible when timing is rejected. Run direct underlying
benchmark argv inside this queue, without a nested `scripts/linux-bench` lock.

## Reusable external-load proof interface

Root owns real-host proof and runner restart. The reusable interface does not
apply readiness on every call; production `Runner` still does so separately:

```python
from bench.perf_queue import JobCPUSampler, SystemHealth, contamination_summary

sampler = JobCPUSampler(job_root_pid, host="linux")  # or "mac"
health = SystemHealth("linux")
samples = [health.sample(cpu_sampler=sampler, deadline=deadline_epoch)
           for _ in range(3)]
summary = contamination_summary(samples)
```

`deadline` is a UTC epoch bound; an optional cancellation Event closes the
partial window. For a controlled proof, root can acquire the canonical EX
lease, wait for >=85% idle once, keep an owned four-worker process group alive,
then take three ten-second samples each for clean, separate three-worker
sibling load, and restored clean. Do not restart the job between phases. This
is distinct from production's unchanged >=80% readiness. No burner or Mac proof
was executed while implementing the policy.

Per sample, the public fields are `total_busy_percent`,
`job_tree_busy_percent`, `other_busy_percent`, `interval_seconds`,
`cpu_accounting_valid`, and `cpu_accounting` provenance. Provenance includes
`attributed_pids`, `attributed_identities` (PID/start), `root_pid`, `root_start`,
before/after member PIDs, per-process endpoint CPU counters, source method,
reasons and scan durations. A proof must require valid accounting and confirm
the external root and children never appear among attributed identities.

Each new attempt stores `contamination_policy: other-busy-v2` and
`contamination: contamination_summary(periodic_health)`. The summary fields are
`valid`, `contended`, `mean_other_busy_percent`, `max_other_busy_percent`, and
`reasons`. A valid summary can still be contended by its measured other load;
forced/rejected/stopped attempts and outside-job memory checks also remain
independent rejection conditions. Consumers must never relabel old attempts
using the new arithmetic.

## Root held-out evaluation

The root policy is frozen before held-out in `bench/gate-1-policy.json` (15%
median-area proposal; no passing tune winner). The Mac source is retained at
`REPO_ROOT/.tmp/m1-final-source-v2`, pipeline fingerprint
`264dcc9b4abfd0c7ca5d7dc0a75143bc0f165a23a18a28e003e801b55d60706f`.
Both held-out jobs migrated before first execution, retaining their original
cwd/source revision in queue metadata. The earlier snapshot remains untouched.
Its `SOURCE-RECEIPT.json` also hashes every Python source. Standalone comparison
jobs retain the earlier immutable139a0555 source; the engine is unchanged, with
the later orchestration fixing forced-plan option consistency and requiring
a closed queue-environment join for gate acceptance.

Held-out measurement job `0cb3636276794a17b2de710d18c318c2` has priority1 and
produces `out/m1-heldout-measure-{attempt}/measurement-plan.json`, with exact
movies/truth/masks and a separate30s sustained run. These retries do no OCR.
Grading job `bbe7774e838b468098e48903b807c97a` has priority3, after currently
queued timed jobs. `bench.queued_heldout` selects the first clean complete
sealed attempt, or the last complete contended attempt if none is clean,
**using only receipt trust before OCR**. Missing plans from rejected preflights
are retained as failures and cannot replace a complete measurement.

Only that selected measurement is graded. Repeated grading-job attempts return
the existing final card, verify retained queue/plan hashes, and do no second
OCR evaluation. A crash after completed bundle grading can reuse that verified
card. No held-out quality result feeds back into tuning. The canonical result
is `out/m1-heldout-final/scorecard.json` and `out/scorecard.json` on the Mac.
It includes the selected queue receipt/hash and requires queue cleanliness in
gate1. Raw bundle cards preserve their original benchmark trust; the final
joined card is authoritative for the milestone. Grading-job CPU load is outside
all measurement clocks and cannot validate a contended measurement.

Selection/no-repeat/corruption cases use synthetic graders with real persisted
queue files in `tests/test_queued_heldout.py`; native OCR and sealed-bundle
validation remain the existing `cross_host` seam. A missing complete measurement
leaves the gate explicitly unfinished rather than inventing zero observations.


## Root native policy proof and live runner hand-off

Root ran the real four-worker / separate three-worker / removed-burner proof
on both hosts after the worker implementation. Linux mean other busy was
3.30%,39.46%,2.18%; Mac3.78%,41.21%,5.47%. All clean/violation/revert checks
pass, all four owned workers are credited, and no foreign worker is credited.
Every known proof identity exited. See `bench/results/other-busy-proof-{linux,mac}.json`.
The Mac command used `--minimum-ready-idle 80 --readiness-period 10`, rather
than the optional85% proof readiness default.

The restored root runners are LinuxPID2773686 and MacPID74976. These are recorded
identities, not safe targets for blind kill. Use the cooperative stop CLI above;
status reports whether their start identities still match. Old runners2644125
and26083 were stopped before deployment, and old labels were retained. The fresh
CPU qualification is an explicitly linked new job; it does not reset or rewrite
any historical attempt. The root comparison receipt summaries are
`bench/results/perf-queue-{linux,mac}.json`; refresh from raw attempts with
`python -m bench.perf_queue_report --host HOST --out out/perf-queue-scorecard.json`
in that host's root venv. The JSON includes per-sample queue source paths and
raw benchmark hashes rather than declaring success from queue exit status.
