# Submission package and session replay

W10 prepares factual submission material and local build-history tools. The owner and Opus write the final script/voiceover, approve footage and publish. Nothing here starts Twitch, Devpost, YouTube or a metered model request.

## Drafts

- `submission/README-PITCH.md`: root README integration proposal.
- `submission/DEVPOST.md`: form copy with missing evidence left as explicit fill-ins.
- `submission/SHOT-LIST.md`: 2:55 edit plan, blocked shots and capture ledger requirements.
- `submission/CLAIMS.md`: architecture and official-source anchors, with current qualification limits.

The natural target is not passed, SRT acceptance is pending, and real Twitch acceptance of the verified forwarder's `tcUrl` needs an attended test. No numeric privacy, speed or app-compatibility claim is added by this workstream. No real footage exists in this package.

## A replay that cannot copy private transcript text

A regex scrubber cannot reliably recognize names, addresses or arbitrary owner data. This tool therefore drops all transcript bodies, tool names, arguments, results, session identifiers, paths and unknown fields before it produces any artifact. It exports only fixed event kinds, normalized UTC timestamps, source line ordinals and a SHA-256 digest of the complete source bytes. Counts describe physical JSONL lines, selected events and excluded records. `event_msg` duplicates are excluded; repeated `response_item` records remain separate source events rather than being claimed as unique work.

The source is an explicitly selected local Codex rollout JSONL file. Supported records are timestamped `session_meta` and `response_item` records (`message` with user/assistant role, function/custom tool request/result). This is a versioned format assumption tested on synthetic data, not yet qualified against a real session. T3 message exports, `codex exec --json` without timestamps, compacted history and arbitrary chat archives are not supported. The tool does not search session storage or open any real log automatically. Missing timestamps, out-of-order selected-format records, malformed JSON, empty selection and size limits fail closed. Size bounds: 1 MiB/line, 128 MiB/source, 100,000 events. The final input path component must not be a symlink. The output directory must be new.

The bundle contains `events.json`, `transcript.txt`, `replay-prompt.txt` and `manifest.json`. The directory uses mode 0700 and files use 0600. Filesystem and parser errors never echo input text or paths. Integrity hashes detect changes relative to the manifest; they are not a signature or attestation. Loading also regenerates the prompt and text from validated fields, so updating a manifest cannot introduce arbitrary prompt/terminal content.

Optional annotations are a separate editor input with a source line ordinal, a fixed milestone (`plan`, `implementation`, `tests-failed`, `tests-passed`, `review`, `commit`, `benchmark`, `fix`) and a full lowercase 40-character commit SHA. No custom caption text is accepted. These annotations are always labeled **editor-supplied-unverified**. They do not prove a test passed or a commit exists. Root must check the commit in Git and correlate the source event timestamp and actual event privately before using it in footage.

## Local synthetic exercise

Use the existing pinned interpreter through its venv path, without resolving the symlink. Adapt only the interpreter path after provisioning on another machine. Commands below create a new synthetic bundle and print static metadata, not real build footage. Use a fresh output directory for each run.

```bash
shield_python=/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export VECLIB_MAXIMUM_THREADS=2 OPENCV_FOR_THREADS_NUM=1 PYTHONDONTWRITEBYTECODE=1
scripts/host-lock shared nice -n 10 "$shield_python" -m tools.session_replay extract \
  --input tools/session_replay/example-session.jsonl \
  --output /tmp/agents/irl-shield/w10/synthetic-review-new
scripts/host-lock shared nice -n 10 "$shield_python" -m tools.session_replay play \
  --bundle /tmp/agents/irl-shield/w10/synthetic-review-new --no-wait
```

Run short functional checks within the agents slice under the canonical SH lease. W10's run receipts record the exact launcher. Any timed playback or recording goes through root's EX performance queue instead of these static commands.

After root authorizes real local extraction, the same `extract` command takes one explicitly selected real rollout path and a new private scratch output. Do not put content, keys or device codes in command arguments. Optional `--since`/`--until` bounds are inclusive RFC3339 timestamps. A private `--annotations` JSON file can select milestone anchors. A complete source SHA still identifies the full source even when the event selection is bounded. Do not upload the raw source, place it in a Git patch, print it to the terminal, or attach it to receipts.

Real-log access is prohibited in W10's current packet. All examples and tests here are synthetic. The real source digest, approved bundle digest, submitted Codex session ID and commit-correlation receipts remain pending.

## Timelapse and optional headless CLI replay

`play --bundle ... --speed 60 --max-gap 0.5` prints events with original UTC timestamps. It divides each original interval by speed, then caps that gap at the declared maximum. This is variable-gap compression, not a claim of constant 60x speed when gaps are capped. The header persists in the captured terminal output and says **SANITIZED SESSION REPLAY / SESSION LOG TIMELAPSE**. For a crop that would remove the header, the editor must keep an equivalent replay label visible. `--no-wait` instead labels a static metadata export. W10 has not recorded either mode as real build footage.

A separate headless Codex CLI run can replay the reviewed metadata through stdin. This is a retrospective model run, not a resumed build session. It must never author project code. [Official non-interactive documentation](https://developers.openai.com/codex/noninteractive/) and the [CLI reference](https://developers.openai.com/codex/cli/reference) describe the flags below; local `codex exec --help` was also checked. No cloud request was made.

Proposed exact inner command, **not executed**:

```bash
codex exec --ignore-user-config --ephemeral --sandbox read-only \
  --skip-git-repo-check --color never --json \
  --model gpt-6.1-sol -C /replay - \
  < /replay/replay-prompt.txt > /capture/cli-events.jsonl 2> /capture/cli-stderr.log
```

These are paths inside a future isolated runner, not host paths to create blindly. `/replay` contains only the approved sanitized bundle and is mounted read-only. `/capture` is its private output directory. The project worktree, raw sessions, personal home and unrelated account data are absent. Use only the approved account's credential mechanism, with no credential in argv/output. Do not resume or fork the submitted session. Do not use bypass flags, add writable project directories or enable integrations.

**Read-only sandbox is not read isolation.** The command above is an inner-command proposal, not a complete host isolation recipe. `--ignore-user-config` still uses `CODEX_HOME` for authentication. The model could request tools despite the prompt, and inherited instructions or integrations could expose data on an unisolated host. Root must prepare and exercise the actual runner's filesystem/tool/network constraints with synthetic canaries, verify no raw/log/worktree mounts and no extra MCP integrations, inspect the exact sanitized stdin, then authorize the metered run. W10 supplies no launcher that can accidentally execute it. No CLI cloud or isolation acceptance is claimed.

Before a real run, root records exact runner argv, CLI binary/version hash, requested model, safe environment-variable names, bundle/prompt hashes, mount/tool policy, expected private receipt paths and cost authorization. Inspect all emitted CLI JSON/stderr locally before recording or sharing. Model output is a new untrusted artifact. It must not be shown as original source text. The deterministic local timelapse is available without a model call, but does not itself fulfill the separate requested headless replay.

## Data flow and proof limits

1. Explicit local file is opened read-only, never modified. Raw bytes exist only in process memory and source hashing; raw JSON is parsed without a raw temporary copy.
2. Fixed-field projection happens before any disk/stdout output. Bodies are withheld rather than heuristically redacted. No imports or subprocess calls in the implementation start a network client, shell or model CLI.
3. Validated metadata writes exclusively to a new private bundle. Existing output, leaf input symlinks and nonregular files are refused. I/O failure may leave partial sanitized artifacts, which are not accepted by `load` without a complete matching manifest.
4. `load` validates hashes, strict fields, timestamps, kinds and regenerated derived files. Playback uses only the bundle, so the original source may be unavailable or removed.
5. Root inspects the approved bundle before any separately authorized export or cloud stdin. A timestamp, digest or fixed annotation can still be sensitive operational metadata; review them too.

The synthetic tests include private-URL, API-key-shape, stream-key-shape, device-code, phone credential, path, address, email, IP, arbitrary ownerdata and terminal-escape canaries. They check every emitted bundle file and terminal output, original input preservation, selection arithmetic, chronology, limits, permissions, tamper refusal, CLI error redaction and offline playback. These tests prove the exercised synthetic contracts, not that a real session was replayed or that arbitrary future formats are supported.

## Integration and acceptance

All new tests are flat `tests/test_session_replay*.py` files discovered by the current Python gate. The gate's compile-only traversal does not list `tools`; importing this module via the replay tests exercises it. Root may add `tools` to that traversal after the shared source fence releases, but no shared gate edit is required for test discovery.

No runtime/CLI/stream integration is needed. Root can link the docs and merge the README proposal after claim review. No new third-party dependencies, models, imagegen assets or media are introduced. The synthetic fixture is newly authored in this Codex child. Its provenance/hash is in `submission/ASSET-MANIFEST.json`.

The W10 handback carries a patch, post-apply hashes, invocation logs, source-freeze gate packet and process audit. The full SH gate remains pending root scheduling until an actual receipt is returned. Local W10 tests cannot substitute for the conductor's required full gate and cross-vendor review.
