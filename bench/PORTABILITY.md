# Linux portability probe

The detector boundary is a uint8 OpenCV BGR frame in, bounded axis-aligned pixel
boxes out. The probe calls the canonical `shield.masking.masked_frame` function,
which uses NumPy and needs no Apple framework. This
probe exercises those stages independently from the macOS VideoToolbox stream
path. It does not measure privacy quality, run OCR judges, or earn a bench gate.
Windows is untested.

All generated clips and stills are **benchmark-only**, with no audio. They may
retain readable third-party names or logos and are not demo-ready assets under
the repository's Hackathon rules.

## Verified runtime scope

This probe uses Python 3.11 and a private environment at
`.tmp/linux-probe/.venv`, with the pins in `requirements-linux-gpu.txt`. The main
CPU/CoreML environment is separate. The Linux target is an i7-7700K and GTX 1080
Ti (Pascal, SM 6.1), driver 580.178.04. No host driver, system CUDA, global Python
packages, Twitch connection, or production records are changed.

The compatibility choice is deliberate:

- [ONNX Runtime's CUDA compatibility table](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#cuda-12x)
  lists ORT 1.20.x with CUDA 12.x and cuDNN 9.x. ORT 1.20.2 was available from
  the package index; 1.20.1 was not offered for this environment.
- [NVIDIA's cuDNN 9.3 support matrix](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.3.0/reference/support-matrix.html#gpu-cuda-toolkit-and-cuda-driver-requirements)
  includes CUDA 12.4, Pascal and compute capability 6.1. Hence cuDNN 9.3.0.75
  and the CUDA 12.4 runtime wheels are pinned together.
- Current [ORT installation documentation](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#requirements)
  says PyPI GPU releases from 1.27 default to CUDA 13. NVIDIA's
  [CUDA architecture archive](https://docs.nvidia.com/cuda/cuda-features-archive/)
  records removal of Pascal library support in CUDA 13. An unpinned latest GPU
  install is unsuitable for this card.

The installed NVIDIA wheels are cuBLAS 12.4.5.8, CUDA runtime/NVRTC 12.4.127, cuDNN
9.3.0.75, cuFFT 11.2.1.3 and cuRAND 10.3.5.147. No Torch install is needed.
ORT 1.20 predates `preload_dlls`; the launcher adds only this private environment's
NVIDIA wheel `lib` directories to its process's library search path.

CUDA uses a 2 GiB provider arena limit, same-as-requested arena growth, the
`HEURISTIC` convolution search and disabled maximum convolution workspace.
[ORT documents](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#gpu_mem_limit)
that its arena limit is not a cap on all device memory. CPU inference and OpenCV
are limited to two threads; jobs run at nice 10 inside `app-t3code-agents.slice`.

## Reproduce

From the repository root, create an isolated environment using Python 3.11 and
install the requirements. Keep its cache and temporary files inside `.tmp`:

```bash
mkdir -p .tmp/linux-probe
python3.11 -m venv .tmp/linux-probe/.venv
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
free -g
uptime
systemd-run --user --scope --slice=app-t3code-agents.slice nice -n 10 \
  env PIP_CACHE_DIR="$PWD/.tmp/linux-probe/pip-cache" \
  TMPDIR="$PWD/.tmp/linux-probe" \
  .tmp/linux-probe/.venv/bin/python -m pip install --only-binary=:all: \
  --report .tmp/linux-probe/install-report.json -r requirements-linux-gpu.txt
scripts/linux-probe --candidate ppocr-v5-mobile \
  --output-dir /tmp/agents/irl-shield/m1-linux-probe/ppocr-v5-mobile --encode
scripts/linux-probe --candidate ppocr-v6-small \
  --output-dir /tmp/agents/irl-shield/m1-linux-probe/ppocr-v6-small --encode
scripts/linux-probe --candidate ppocr-v6-tiny \
  --output-dir /tmp/agents/irl-shield/m1-linux-probe/ppocr-v6-tiny
scripts/linux-probe --candidate ppocr-v6-medium \
  --output-dir /tmp/agents/irl-shield/m1-linux-probe/ppocr-v6-medium
```

Run one candidate at a time, after checking room on the shared machine. The
script prints memory/load before launch. A missing or inactive CUDA provider
throws. A completed CUDA probe must also contain profiled CUDA kernel events;
provider enumeration alone is insufficient. Unsupported operators may be
partitioned to CPU, and the profile records both providers' kernel events.
Runtime fallback after session construction is disabled.

Each candidate uses the same 20 actual frames, sampled evenly over the middle
80% of the licensed five-second `sf-market` tune fixture. The first two frames
warm each provider; timing distributions use the remaining 18. Input file and
frame SHA-256 hashes bind comparisons to identical source data. The probe
checks finite, bounded, nonconstant probability maps; bounded nonempty boxes;
nonempty opaque masks; exact preservation outside the masks; and real image
variation after masking. CUDA probability maps must stay within .01 maximum
absolute difference from CPU. Sample PNGs and full numerical results are saved.

The optional serial pipeline decodes all 150 frames, detects and masks each,
and encodes to H.264 with NVENC. It verifies the encoded frame count with
ffprobe. This is a short unpaced file pipeline, without ingest, transport,
scheduling, temporal persistence, OCR evaluation, or a sustained-load claim.
The CPU/GPU inference comparison includes profiler overhead. Shared-machine
contention and an older GPU-specific ORT build limit cross-machine comparisons.

## Results and receipts

The initial v5 mobile and v6 small probes passed on Linux on 2026-10-29. Input was 1280×720 video,
preprocessed to a 1×3×544×960 tensor. Timings below use 18 measured frames after
two warmup frames, under concurrent shared-machine load (1-minute load averages
6.67 and 6.87 at probe start). These CPU results use the GPU environment's ORT
1.20.2 CPU provider, not the main environment's newer ORT build.

| Candidate | CPU mean / p95 inference | CUDA mean / p95 inference | Boxes, CPU = CUDA (20 frames) | Maximum probability difference | Serial CUDA + NVENC pipeline |
| --- | --- | --- | --- | --- | --- |
| PP-OCRv5 mobile | 234.61 / 261.34 ms | 12.06 / 12.42 ms | 276 | 0.0000430 | 150 frames, 21.53 fps |
| PP-OCRv6 small | 207.05 / 272.09 ms | 14.31 / 14.79 ms | 294 | 0.0000191 | 150 frames, 21.49 fps |

CUDA profiles contain 5,600 and 3,800 CUDA kernel events respectively. Integer
detection boxes match the corresponding CPU boxes exactly on every sampled
frame. Every mask is opaque, preserves all outside pixels exactly before
encoding, and leaves real image variation. Masked area ranges are 3.62–7.54%
for v5 and 5.47–7.87% for v6. No result here selects the privacy-quality winner.

An artifact audit also decoded encoded frame 78 for each candidate. Outside-mask
mean absolute error from the source was 2.98 and 2.91 pixel levels, with strong
image variation remaining. Both NVENC files contain all 150 frames. Masked PNGs
were visually inspected; numerical checks of source, mask-only and decoded
output PNGs confirm image variation and opaque text regions.

A later extension at 23:02 UTC on the same date verified the already downloaded
v6 tiny and medium artifacts with the existing environment, without installing,
downloading, exporting or rewriting models. These runs used the identical 20
source-frame hashes as both initial candidates, the same 1×3×544×960 tensor
shape, two warmup frames and 18 measured samples. Their 1-minute load averages
at the recorded inference preflight were 1.74 and 1.82 respectively, so their
rates should not be treated as an uncontended comparison with the earlier runs.

| Candidate | CPU mean / p95 inference | CUDA mean / p95 inference | CPU / CUDA inference rate | Boxes, CPU = CUDA (20 frames) | Maximum probability difference |
| --- | --- | --- | --- | --- | --- |
| PP-OCRv6 tiny | 66.01 / 75.45 ms | 9.36 / 9.81 ms | 15.15 / 106.81 Hz | 238 | 0.00008491 |
| PP-OCRv6 medium | 714.61 / 803.59 ms | 37.27 / 41.81 ms | 1.40 / 26.83 Hz | 293 | 0.00004035 |

The rates above are the inverse of mean inference time, including ORT profiler
overhead; they are not emitted-video frame rates. Raw CUDA profiles contain
3,800 and 4,480 CUDA kernel events respectively, with no profiled CPU kernels in
those CUDA sessions. CPU and CUDA boxes match exactly on every sampled frame.
Probability maps remain finite, bounded and nonconstant. All numerical opaque
mask and outside-pixel checks pass; the independently reread saved PNGs also
match byte-for-byte between CPU and CUDA. Masked areas range from 2.87–6.86%
for tiny and 3.74–7.38% for medium. Neither extension requested encoding, ran
OCR judges or established privacy quality, sustained performance or a gate.

Raw receipts live in `/tmp/agents/irl-shield/m1-linux-probe/`:

- `ppocr-v5-mobile/summary.json` and `ppocr-v6-small/summary.json`: frame hashes,
  complete package lists, source/model hashes, all per-frame boxes, numerical
  assertions, timings, provider options and encoded-file metadata.
- `artifact-audit.json`: independent reread of both summaries, identical-frame
  checks, exact box comparison, source-hash checks, decoded-output fidelity and
  confirmation that installed versions match every requirements pin.
- The two initial candidate directories contain raw ORT profiles, sample PNGs, the encoded
  clip and an ffmpeg log; sibling `.log` files capture the launched commands.
- `ppocr-v6-tiny/` and `ppocr-v6-medium/` contain their `summary.json`, separate
  `cpu.json`/`cuda.json`, raw ORT profiles, PNG samples, exact `command.json`,
  `preflight.json`, `probe.log`, `exit.json` and `artifact-audit.json`. These two
  directories contain no encoded clip. `v6-tiny-medium-artifact-audit.json`
  independently rereads timings, profiles, exact boxes, mask pixels, all four
  candidates' frame hashes, and live model/source hashes.
- `v6-tiny-medium-process-cleanup.log` confirms both extension scopes are
  inactive/dead. Both jobs exited zero; no process was retained and no other
  session's process was stopped.

Environment receipts live in `.tmp/linux-probe/install-report.json`,
`nvrtc-install-report.json`, `install.log`, `nvrtc-install.log`, `cuda-ldd.txt`
and `license-inventory.json`. The install reports record wheel URLs and SHA-256
values. The first v5 attempt produced a valid CPU run, then failed closed on
missing `libnvrtc.so.12`; it is retained under `ppocr-v5-mobile-before-nvrtc/`.
Adding the matching NVRTC wheel resolved that linked-library failure. The single
retry above passed. An earlier import-only diagnostic followed the canonical
masker moving from `bench.metrics` to `shield.masking`; it ran no inference.

Verdict: all four raw ONNX detectors and the canonical opaque masker work on Linux
CPU and on this Pascal GPU with the pinned runtime. The short serial GPU
pipelines tested for v5 mobile and v6 small remain below the 30 fps source rate
in those runs; tiny and medium have no encoded-pipeline measurement here. CPU-only full-pipeline
throughput, sustained GPU load, transport/streaming, privacy-score equivalence,
other Linux GPUs and Windows remain outside this probe's evidence.

## Sources and licenses

The four detector artifacts remain hash-pinned in `models/manifest.json`, with
Apache-2.0 source/license references there. Fixture attribution is in
`fixtures/ATTRIBUTION.md`; `sf-market` is CC BY 3.0. Local sample frames and encoded
outputs are derivatives of that attributed fixture, without audio.

[ONNX Runtime GPU 1.20.2](https://pypi.org/project/onnxruntime-gpu/1.20.2/)
is MIT licensed. RapidOCR and the detector models are Apache-2.0; the existing
base dependency license inventory is `models/licenses/dependencies.json`.
New ORT 1.20 transitive packages are `coloredlogs` 15.0.1 and `humanfriendly`
10.0 (MIT), plus `sympy` 1.14.0 and `mpmath` 1.3.0 (BSD). Their installed
metadata receipts are in `.tmp/linux-probe/license-inventory.json`; package
sources are [coloredlogs](https://pypi.org/project/coloredlogs/15.0.1/),
[humanfriendly](https://pypi.org/project/humanfriendly/10.0/),
[SymPy](https://pypi.org/project/sympy/1.14.0/) and
[mpmath](https://pypi.org/project/mpmath/1.3.0/).
NVIDIA runtime wheels carry proprietary NVIDIA terms, rather than an open-source
license: [cuDNN wheel metadata](https://pypi.org/project/nvidia-cudnn-cu12/9.3.0.75/),
[cuDNN 9.3 software license](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.3.0/reference/eula.html)
and [CUDA 12.4 EULA](https://docs.nvidia.com/cuda/archive/12.4.1/eula/index.html).
This probe installs those wheels locally; it does not bundle or publish them.
cuBLAS, CUDA runtime, NVRTC, cuFFT and cuRAND use the CUDA license above; cuDNN
uses the linked cuDNN license. All wheels installed without a service account,
paid API, waitlist or expiring backend. The proprietary license terms still apply.
The installation report retains metadata/license receipts without copying
additional license snapshots into the repository.
