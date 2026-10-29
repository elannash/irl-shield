# IRL Shield

IRL Shield is an experimental privacy relay for IRL video. Its masking engine
looks for readable location clues and covers them before presentation. A delayed
frame clock gives asynchronous detector lanes time to work; missing coverage
produces a protected frame, and a local HOLD produces a slate.

Milestone 1 builds the measurement system and compares offline detectors. Live
phone ingestion, Twitch publishing, chat commands and Shield Mode are later work.
The local RTMP/SRT experiment is separate groundwork, with its measured limits in
[docs/M2-GROUNDWORK.md](docs/M2-GROUNDWORK.md). It is not a production relay.

The engine accepts timestamped in-memory BGR frames independently of transport.
Apple Vision is available on macOS; PP-OCR models use ONNX Runtime on CPU, Core ML
or CUDA. Linux CPU/CUDA execution has been exercised; Windows remains untested.
The selected configuration and its hardware requirements will be recorded with
the final M1 scorecard. A configured 30fps source is never treated as measured
30fps output.

From the Linux checkout, the Mac wrapper synchronizes source and provisioned
assets, runs a bounded command and leaves all generated media out of git:

```sh
scripts/mac scripts/setup
scripts/mac --seconds 14400 scripts/bench --candidate ppocr-v6-tiny \
  --split tune --run-id tune-example
scripts/collect
```

`scripts/bench` provisions hash-pinned fixtures/models and writes
`out/scorecard.json` plus an immutable run directory. The final documented gate
recipe will add the selected lane settings, tune-derived median-area ceiling and
30s sustained workload. Held-out is reserved for the final milestone evaluation.

The measuring stick covers Latin-script text and Arabic digits observed by
Tesseract `eng`, Vision accurate `en-US`, and PP-OCRv5 English-mobile. Natural
truth requires input confidence at least .9 on two frames; output readings at
.5 can expose a leak. Every visible synthetic label counts. Non-Latin text,
natural text all input judges miss, and single-frame-only natural text remain
unproven. See [bench/README.md](bench/README.md) for the full scoring contract.

Fixtures are licensed CC0 or CC BY, attributed in
[fixtures/ATTRIBUTION.md](fixtures/ATTRIBUTION.md), and muted. They contain
third-party names and logos and are **benchmark-only**, including masked outputs
and previews. No current clip or still is designated demo-ready. Model weights,
download revisions, hashes and licenses are in
[models/manifest.json](models/manifest.json); candidate sources and portability
are in [bench/DETECTORS.md](bench/DETECTORS.md) and
[bench/PORTABILITY.md](bench/PORTABILITY.md).

Architecture decisions and qualifications are recorded in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Experiment history, including rejected
changes, remains in [bench/LOG.md](bench/LOG.md). Built in the owner-designated
Codex thread and its Codex children for the Codex x TwitchCon hackathon.
