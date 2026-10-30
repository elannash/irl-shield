# GStreamer transport lane

This is an optional transport implementation behind the existing
`bench.clocked_pipeline.drive` source/sink interface. `shield/engine.py`, its
render/motion/control/worker modules, and common bench files are unchanged.
The common pipeline fingerprint at the assigned base is
`17ec5477dc6f6f02d6c2370cc4e4e8726de2fe91eea1a244b9977a18b8a40b18`.

The implementation is under `relay/gst*.py`. Current measurements and limitations
are in [LOG-gst.md](../bench/LOG-gst.md). Installation or an available plugin alone
is not evidence of successful sustained output or privacy quality.

## Data path and ownership

- File input uses `filesrc → qtdemux → h264parse → nvh264dec/vtdec`.
  SRT input uses `srtsrc → tsdemux`; RTMP input uses `rtmp2src → flvdemux`.
  RTMP is a pull from a local/Tailscale server such as MediaMTX, not an RTMP
  listener implemented by this module.
- Decoded frames branch through a bounded tee. GStreamer `videoscale` produces
  the fast/accurate detector copies, each paired by exact source PTS with the
  full BGR frame. Full and reduced appsinks have two-buffer backpressure.
  A bounded source-indexed cache keeps the copies alive until lane offer.
- `CopyLane` offers reduced frames to the existing `DetectorLane` workers and
  rescales each returned quad separately in x/y to full-frame coordinates.
  Workers retain newest-frame scheduling and original index/completion time.
  Missing copies fail explicitly. Copies are read-only like engine-owned detector frames. No full-frame fallback hides a pairing error.
- The unchanged `MaskingEngine` alone decides LIVE/PROTECT/HOLD, masks, motion,
  coverage and presentation deadlines. The source queue is bounded; a dropped
  source index becomes a gap at the engine clock. SRT uses media PTS with PCR scheduling ignored, tolerating one90kHz tick;
  RTMP permits its1ms timestamp quantum. Raw timestamps/errors are retained.
  Larger invalid input PTS cadence errors fail the connection rather than silently relabelling frames.
- A finite live source signals EOS at its declared source-clock end to drain
  decoder-held tail frames; SRT itself is not a finite-file EOF protocol.
- `GstSink` accepts only `PresentedFrame`, then uses
  `appsrc → videoconvert → nvh264enc/vtenc_h264 → h264parse → mux`.
  NVENC uses p4, ultra-low-latency, CBR, zero B frames/lookahead and zero latency.
  VideoToolbox uses realtime mode and disables frame reordering. Actual options
  are retained in each receipt. GPL `x264enc` is an explicit CPU fallback, used
  only by tiny synthetic transport unit tests in this lane.
- File egress is MP4. SRT is `mpegtsmux → srtsink`. RTMP is
  `flvmux → rtmp2sink`. Network URLs pass the existing `relay.media.local_url`
  guard: literal localhost/Tailscale address, explicit owned port, RTMP/SRT,
  no embedded username/password. No Twitch endpoint or stream key is supported
  by this lane.
- AAC ingest is decoded to mono 48kHz S16LE. Audio is queued outside the engine
  and released only up to emitted video PTS. PCM is split at sample boundaries;
  D is the wall-clock wait, not an extra addition to audio PTS. The egress
  audio appsrc encodes AAC. `--audio` requires an actual AAC input stream;
  missing audio fails rather than fabricating samples.

For a detector at source width, its copy reuses the already-owned full frame;
only smaller widths add a scaled branch. Mapped native buffers are copied into owned NumPy pixels before sample release.
The engine takes its existing snapshot. Egress copies presented pixels into an
owned GStreamer buffer. This is **not zero-copy**, a GPU renderer, or retained
CUDA full-frame ownership. All masking remains in the unchanged renderer. A
GPU draw path is deferred until measured copy/encode costs justify it.

The ctypes adapter dynamically links the installed GStreamer C libraries. It
uses installed GObject Introspection typelibs for public record offsets and
sizes, including BGR stride/plane metadata, rather than assuming C layouts.
This allows the tested Python 3.11 detector runtime to use Linux's GStreamer
without requiring its Python 3.14 PyGObject extension. Missing libraries,
typelibs, fields, plugins or native errors surface as errors. It is deliberately
a small transport binding, not a general GStreamer Python SDK.

## Setup

Keep all Python installs in `.tmp/gst/.venv`; never install into another lane's
venv or a global interpreter. Existing model/runtime pins and their licenses
remain in `requirements-models.txt` / `requirements-linux-gpu.txt` and
`models/licenses/dependencies.json`. A fresh judge setup may install those pins
in its own venv. This lane initially uses a private venv with read-only `.pth`
references to already installed, pinned packages; it changes no shared package.
The runtime receipt identifies the packages that actually loaded.

Linux needs the system GStreamer core/app/video libraries, introspection
typelibs, base/good/bad/libav plugins and NVIDIA driver. The owner installed the
Linux plugins before this lane. `nvh264enc` and `nvh264dec` must be present;
`cudaconvert`/`cudascale` are not required for the CPU engine transport.

On macOS, the owner authorized `brew install gstreamer` after the root receipt
marker. The lane's bounded sync helper runs only in `~/code/irl-shield-gst`,
excludes `.git`, builds, outputs, temp directories, venvs and model/fixture
caches, and executes in `bash -lc`. Create that mirror's private venv first.

```sh
relay/gst_mac mac-install --out out/gst-install
relay/gst_mac inspect --out out/gst-runtime
```

Model source weights may be linked individually from the read-only existing
model cache into this lane's `models/cache`. Static ONNX derivations go into
this lane's cache; never point the writable static-derivation directory at the
root cache. Weights, licenses and SHA-256 values remain pinned by
`models/manifest.json`; no new model or dataset is introduced.

## Measurement and grading

All heavy commands check `/tmp/agents/irl-shield/m1-20261029-ready.json` for
`complete:true` before loading models. Root `valid:false` means its receipt
completed; it does not certify this lane's run. Each lane run independently
checks START/END pressure. The CLI holds the common
`/tmp/agents/irl-shield/perf.lock`: EX for timing/relay/A-V, SH for
inspection, untimed setup (including brew/pip/media/model work) and grading.
Root may retain EX through additional comparison trials after its marker;
`complete:true` permits attempting the lease, never bypassing it. The descriptor survives exec. Readiness is checked again after acquiring the
lease so a corrected marker can revoke a queued operation. Do not wrap
these commands in another independent acquisition of the same lock.

The conductor now owns timed scheduling through `scripts/perf-queue`. Do not
start manual timed runs in this lane. Each timed job enters through
`relay/gst_job`, which caps pools/nice, keeps Linux inside the T3 slice, and
passes `--queued` to skip the inner lock. The external runner must already
hold EX. The command validates the inherited descriptor against the canonical
lock's device/inode and retains `queue-context.json`. Linux requires the
runner's inherited `app-t3code-agents.slice`; the wrapper neither creates a
new scope nor escapes the runner's process group. Root completion is still
checked; the queued command never flocks.
`relay/gst_queue_jobs.json` supplies exact direct argv/cwd, priority2, unique
`{attempt}` outputs, expected receipts and prerequisites for ten jobs. The
root sustained job has priority1. `IRL_SHIELD_PERF_QUEUE_FORCED=1` automatically
sets diagnostic mode and can never produce an accepted performance receipt.
Use the absolute root checkout CLI; queue storage does not follow this cwd.

Example direct job (the runner substitutes `{attempt}`):

```sh
/home/elan/code/irl-shield/scripts/perf-queue enqueue linux gst-linux-example \
  --lane gst --priority 2 --cwd "$PWD" \
  --receipt 'out/gst-queued-linux-gst-{attempt}/measurement-plan.json' -- \
  ./relay/gst_job measure \
  --source-dir /home/elan/code/irl-shield/out/offline-ppocr-v5-mobile-a30 \
  --out 'out/gst-queued-linux-gst-{attempt}' --candidate ppocr-v6-small \
  --transport gst --options .tmp/gst/options-linux-gst.json
```

Mac jobs need the GStreamer setup and exact prepared inputs staged first.
Untimed setup/quality holds SH, and long untimed work must not start once timed
jobs are queued on that host. The lane timebox remains binding even when the
conductor's queued jobs run overnight. No Mac install, timing or quality result
is implied by the job packet.

Use only all seven tune clips (natural and synthetic variants). The input
folder must contain existing prepared `*-input.mp4` and `*.truth.json` files;
no variant generation, external request or held-out access occurs here. Exact
prepared source/truth hashes are retained. A `--clip` run is explicitly a pilot.
The default adds 10s warmup to each quality run, then measures a separate 30s
steady trial. Configure provider/rates/widths once in JSON; `static_model:true`
is the default. Use the same JSON with encoder names adjusted to compare
`--transport ffmpeg`. The `ffmpeg` comparison uses the existing paced OpenCV decode and FFmpeg
rawvideo sink. `--transport nut` uses an actual FFmpeg decode → raw NUT →
PyAV → raw NUT → FFmpeg path through the same source/sink seam. Its default
CPU decode matches the existing relay; `decode_hardware:true` is explicit and
recorded. The NUT comparison is video-only; older relay A/V measurements
remain separate. All three use identical prepared bytes and detector options;
transport codec flags and decode implementations are retained and can differ.

`measurement_windows`, `performance_trust`, `score_video`, `clock_guards`,
`aggregate_card`, and the sealed `bench.cross_host` bundle are reused. Quality
judges are never resident during timing. The common fingerprint stays separate
from the transport fingerprint; `gst-runtime.json` retains the exact transport
source text, plugin descriptions/licenses and runtime versions. The sealed
plan binds every input/output/mask/receipt byte. Changing source after sealing
requires grading the frozen snapshot, not editing its receipt.

```sh
# On the isolated Mac mirror with the frozen common source and judge runtime:
.tmp/gst/.venv/bin/python -m relay.gst_run grade \
  --plan out/gst-linux-tune/measurement-plan.json
```

Per-process GStreamer registry/cache paths stay under `.tmp/gst/`; CUDA wheel
library paths affect only the launched process. The Linux launcher searches its
own venv first and can read the existing owner runtime as a development fallback.

Grading uses Tesseract eng, Vision accurate en-US and PP English recognition.
The common scorer gives no privacy credit to all-slate/black/protected output.
Without independent OCR, privacy metrics remain **unmeasured**, never zero
leaks inferred from missing readings. Warmup/startup remain separate. A healthy
30s post-warmup window, decoded frame/PTS completeness, p95 latency, protection,
CPU, memory and actual observed packet rate are required for a performance
verdict. Short/offline ideal scheduling never establishes wall-clock fps.

GStreamer observes a parsed encoded H.264 access unit immediately before mux;
FFmpeg observes progress-counter updates immediately before mux submission.
Neither observes viewer arrival or network-sink completion. Network latency
and received-output quality require an additional received-media receipt.
The GStreamer file-cycle reopen cost is included in measurements and retained
as pipeline descriptions; the comparison does not hide decoder restart costs.

## A/V and local relay

```sh
# Direct foreground argv for the external queue, never a manual timed run.
./relay/gst_job av --out 'out/gst-av-{attempt}'
./relay/gst_job relay \
  --input 'srt://127.0.0.1:18731?mode=listener' \
  --output 'srt://127.0.0.1:18732?mode=caller' \
  --audio --seconds 40 --out 'out/gst-local-relay-{attempt}'
```

The authored CC0 synthetic A/V control uses seeded texture, two white patches
and two 1kHz sine beeps. It contains no music, text or logos. It measures both
source and re-encoded A/V offsets, reports the introduced difference, and
fails if either event is missing. Event resolution is one video frame plus a
1ms audio envelope bin. It is a four-second control, not sustained performance
or detector quality. Benchmark street clips are **benchmark-only**, never
claimed demo-ready.

## Licenses and distribution

No GStreamer, vendor SDK, model weight, external fixture or Python package
binary is committed by this lane. Actual installed plugin license strings are
saved by `gst-inspect-1.0` in `gst-runtime.json` (and install receipts on Mac).
Linux installed copyright receipts are retained under `.tmp/gst/licenses/`;
they distinguish runtime-library files from scanner/tool licenses.

| Component | License/source | Use and distribution consequence |
| --- | --- | --- |
| GStreamer core, base/good/bad plugin code, GstApp/GstVideo | LGPL-family (installed copyright includes LGPL-2.0-or-later and LGPL-2.1-or-later); [upstream license](https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/main/LICENSE) | Dynamically linked installed libraries. Keep LGPL notices/source and relinking obligations when distributing binaries. Individual plugins can differ. |
| GObject Introspection / GIRepository | Runtime LGPL-2.0-or-later, selected embedded code LGPL-2.0 or MPL-1.1; scanner/tools include GPL-2.0-or-later; [upstream copying file](https://gitlab.gnome.org/GNOME/gobject-introspection/-/blob/main/COPYING) | Installed typelib metadata and shared library; no PyGObject package is added. |
| nvcodec GStreamer plugin | Installed plugin reports LGPL; [plugin documentation](https://gstreamer.freedesktop.org/documentation/nvcodec/nvh264enc.html) | Requires a compatible NVIDIA driver/device. The NVIDIA driver/Video Codec SDK has separate vendor terms; LGPL does not grant rights to vendor binaries. |
| applemedia / VideoToolbox | GStreamer plugin LGPL; Apple framework under macOS terms; [plugin documentation](https://gstreamer.freedesktop.org/documentation/applemedia/vtenc_h264.html) | Native Mac framework, no Apple binary redistributed. |
| SRT plugin / libsrt | Plugin LGPL; libsrt MPL-2.0; [libsrt license](https://github.com/Haivision/srt/blob/master/LICENSE) | System dynamic dependency; preserve applicable library notices when packaging. |
| gst-libav / FFmpeg AAC | Actual installed gst-libav build/license recorded; [FFmpeg legal](https://ffmpeg.org/legal.html) | Build flags can change obligations. Do not label a GPL-enabled FFmpeg build as LGPL-only. |
| x264enc / x264 CPU fallback | GPL-2.0-or-later; [plugin documentation](https://gstreamer.freedesktop.org/documentation/x264/index.html) | Explicit opt-in test/fallback. A distribution bundling it needs GPL review; do not silently enable it in a claimed LGPL-only binary bundle. |
| PyAV16.0.1 (NUT comparison) | BSD-3-Clause wrapper; installed FFmpeg libraries report LGPL version3 or later, with their exact build configuration retained in `.tmp/gst/pyav-libraries.json` | The build also lists x264/x265; their separate terms remain relevant. A core-library license string does not waive dependency notices. No binary is bundled. |
| Synthetic flash/beep control | CC0-1.0, authored by this Codex lane on 2026-10-29 | No third-party data, readable names/logos or music; generated only in lane outputs. |

H.264/AAC patent rights are separate from software copyright licenses. Judge
setup uses publicly available free packages and local hardware; no paid
service, account, waitlist or expiring backend is introduced.
