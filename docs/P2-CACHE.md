# P2 cache identity hand-back

The judge cache now includes installed OpenCV distribution versions and the
canonical path and SHA256 of the active English Tesseract language file.
Identity schema 3 gives these readings a new namespace; historical entries
remain untouched. Scoring, truth selection, output leak checks, thresholds,
labels and detector policies are unchanged.

## Base and reproduced finding

- Worktree: `WORKTREE_t3-e0626c2b`.
- Branch: `elannash/q-p2-cache`, renamed in place from `t3/q-p2-cache`.
- HEAD/base: `631dc5b9bf7cb90c84f0d4aebf430fdcf24eb89c`, initially clean;
  `git diff 631dc5b 0648e0f64d599b223d101f6643ed7d75a36331e3` was empty.
- Finding: `claude:judge-cache-omits-opencv-tessdata` in
  `OWNER_TMP/agents/twitchcon-hackathon/conductor/pr1-review-claude-r2.json`.
  Source SHA256: `2ce576b4fe509c13e92ad17432efc42631b8a4cd35d20651728d89c0d0d1cbbf`.
- Read the original `bench/judges.py:20–35`: its runtime identity included
  binary/package versions and macOS, but no OpenCV or traineddata identity.
  Original file SHA256:
  `db94fa805ba34b55bb75479cf09e64fa11ab413d0330f9d63bac8358a13414b7`.

## Discovery and error behavior

The exact discovery argv is:

```python
[pytesseract.pytesseract.tesseract_cmd, '--list-langs']
```

`subprocess.check_output` uses text output, merged stderr and a 30-second timeout.
It inherits the same environment and working directory as OCR. It passes no
`tessdata-dir` override, so the configured executable resolves its own effective
path, including `TESSDATA_PREFIX` and compiled defaults. No filesystem search or
host-specific directory fallback is used. No OCR runs during discovery.

The implementation parses exactly one native directory report, requires `eng`
in the language list, resolves `<reported-directory>/eng.traineddata` strictly
through symlinks, and hashes the actual file bytes. `Judges.read()` explicitly
passes `lang='eng'`, preserving the existing English scope.

Primary source for the native report is Tesseract's
[`PrintLangsList`](https://github.com/tesseract-ocr/tesseract/blob/5.5.0/src/tesseract.cpp#L285-L294),
which prints `GetDatapath()`. The same source marks `--list-langs` as a
[non-OCR mode](https://github.com/tesseract-ocr/tesseract/blob/5.5.0/src/tesseract.cpp#L438-L440).
[`CCUtil::main_setup`](https://github.com/tesseract-ocr/tesseract/blob/5.5.0/src/ccutil/ccutil.cpp#L31-L89)
resolves environment and compiled defaults, including ignoring a nonexistent
prefix in this version. Discovery trusts the executable's report rather than
reimplementing those choices.

Missing or multiple directory reports raise `RuntimeError`; missing English
language/file raises `FileNotFoundError`. Filesystem errors retain their type,
so an absent data file is not mislabeled as an absent executable. Command errors
raise a discovery `RuntimeError` with the original cause. Identity resolution
precedes reader creation. An `ExitStack` closes any readers already created if
later constructor work fails.

OpenCV versions come from `importlib.metadata.version` for all installed wheel
flavors: `opencv-python-headless`, `opencv-python`,
`opencv-contrib-python-headless`, and `opencv-contrib-python`. The installed
versions, including the wheel revision, enter identity. No installed distribution
metadata raises `PackageNotFoundError`; it does not become a versionless cache.
No new dependency, asset or license was introduced.

## Regression seam and proof

Tests exercise `Judges` construction, `read()` and `close()` with real cache
files and temporary language-file bytes. External OCR engines, package metadata
and OS commands are the substituted boundaries. A separate test launches a real
synthetic CLI executable (never an OCR engine) with a spaced executable/data path,
an inherited prefix, symlinked data and a native-default report when a prefix is
invalid. It verifies the configured command and canonical file, without needing a
Mac or installed Tesseract. This proves the launch/parse/hash wiring, not actual
native OCR or every vendor build's CLI output.

Each added test owns a distinct cache/lifecycle contract:

- OpenCV-only upgrades: each supported distribution flavor must miss while an
  identical environment hits; old version tests did not cover OpenCV metadata.
- English bytes-only and path-only changes: each must miss independently with
  fixed binary version; real file bytes prevent a binary-version-only pin from
  satisfying the test. The bytes case also preserves historical cache bytes.
- Native-command wiring and data failures: configured command/environment,
  canonical symlinks, absent/ambiguous reports, missing data, and command failure
  causes; these were absent from the previous binary-version tests.
- Constructor failures: real fake-reader lifecycle state confirms cleanup after
  recognizer failure and after cache-directory failure.
- GPU ORT metadata: covers the existing CPU-package-missing fallback without any
  GPU session. Existing binary, CPU ORT, pytesseract, RapidOCR, macOS, source and
  shape checks remain; dtype is now checked too.

No production test-only flag or reset hook was added. These tests catch stale
OCR reuse and leaked readers; they do not measure readability or native OCR
accuracy.

Evidence is in `out/p2-cache/` (gitignored):

- Initial red/green: `02-opencv-red.log` / `03-opencv-green.log`,
  `04-tessdata-red.log` / `05-tessdata-green.log`,
  `06-constructor-red.log` / `07-constructor-green.log`.
- Full affected suite: `08-discovery-and-guards.log`, 11 tests passed.
- Final tests against the original implementation:
  `mutation-original-red.log` has six cache-hit failures across three tests;
  `mutation-original-green.log` passes after restoring the fix.
- Independent mutations: `mutation-opencv`, `mutation-data-bytes`, and
  `mutation-data-path`, each with `.diff`, `.json`, `-red.log`, and `-green.log`.
  Omitting OpenCV fails all four flavor cases. Replacing the data SHA256 with
  a binary-version pin fails the bytes-only case. Omitting the resolved path
  fails the path-only case. Each failure is `AssertionError: 1 != 2` (stale OCR
  reuse), not an import/syntax failure. Each restoration is byte-for-byte.
- `runs.jsonl` records every exact test command and exit code. Invocation 1 was
  an environment failure (`pytesseract` absent), not red proof. The existing
  OpenVINO worktree's Python environment was then used read-only; no installs
  or inference were performed.

All proof mutations restore `bench/judges.py` to SHA256
`a73b165bbf248dad134b9c435ae5be38ec95ebfe2a9986ac14e9e0c7fb7c7d1a`.
Final test source SHA256:
`5acce1d2a57da25c685f00bb6ea6e69ba2518cfa15e6ba52932664783d442d33`.

## Final Linux verification and remaining parent work

The final Linux functional run is `17-linux-functional.log`: both unittest
suite discoveries (`tests`, `tests/m2`): 116 tests ran in 32.263 seconds,
115 passed and the macOS VideoToolbox test was skipped. Python compilation of
`bench`, `fixtures`, `models`, `shield`, and `relay` passed. The process exited 0.
Its result is also recorded in `handback.json`.

Runs use `app-t3code-agents.slice`, niceness 10, native worker environment caps
of 2, and OpenCV threads 1. The full-run harness redirects only three legacy
tests' fixed scratch roots into `/tmp/agents/irl-shield/p2-cache/`, and writes
compiled bytecode there. Tests themselves, their assertions and production
behavior are unchanged by that relocation. The harness and mutation drivers
are copied into the evidence folder for repeatability.

Tesseract is absent on this Linux host. No native Tesseract/Mac OCR or quality
bench was run, and no new quality numbers are asserted. The parent owns native
Mac verification, its full gate, and stopping/restarting the queued fresh judge
with schema 3 identity before accepting Q1–Q3 numbers. Runtime inputs must stay
fixed for each `Judges` instance, as in the existing constructor-time identity
contract; restart after environment/data changes.

Only `bench/judges.py`, `tests/test_judge_cache.py`, and this document are source
changes. They are left uncommitted and unstaged for root integration and Opus's
first Q commit. No subagents, publishing, credentials, Mac jobs or model work
were used.
