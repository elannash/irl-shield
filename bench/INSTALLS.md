# Milestone1 install inventory

The Mac already had macOS27, Xcode27, Python3.11 and FFmpeg8.1.2. No service,
secret, paid API, host driver or global Python package was added. Exact observed
versions, including retained older Homebrew kegs, are in
[`results/environment.json`](results/environment.json). This is an environment
receipt, not a performance measurement.

## Mac

`scripts/setup` installed Homebrew **Tesseract5.5.4**. Its dependency transaction
installed or upgraded **brotli, libpng, freetype, libunistring, fontconfig, pcre2,
glib, xorgproto, libx11, libxrender, cairo, icu4c@79, jpeg-turbo, harfbuzz,
openjpeg, leptonica, libarchive, fribidi, libdatrie, libthai and pango**.
Homebrew's automatic update installed its **portable Ruby4.0.9** runtime and
refreshed formula metadata; that is distinct from the existing Ruby formula.

The separately authorized M2 groundwork installed **srt1.5.7_1,
openssl@4 4.1.0 and ca-certificates2026-10-20**. Homebrew also unlinked the
OpenSSL3.6.4 default symlinks; its keg remains. The default `openssl` then resolved
to4.1.0. This transitive side effect was retained and reported, with no manual
relink/removal. FFmpeg stayed8.1.2: SRT transport uses the separately installed
`srt-live-transmit`, rather than replacing FFmpeg. See
[`docs/M2-GROUNDWORK.md`](../docs/M2-GROUNDWORK.md) for the transaction/lifecycle receipt.

All Python packages are repo-local. Main Mac `.venv` contains every exact package
and version listed in `results/environment.json`: the pins in `requirements.txt`,
`requirements-models.txt` and `requirements-relay.txt`. This includes the later
**onnx1.23.2, ml_dtypes0.6.0, typing_extensions4.16.0 and av16.0.1** additions.
The isolated M2 environment contains only **PyAV16.0.1, NumPy2.2.6 and
OpenCV headless4.11.0.86**, plus normal virtual-environment tooling. There was no
source compilation for those wheels.

## Linux

Validation environments live only in ignored `models/.venv`, `models/.venv311`,
`.tmp/m2/linux-venv`, `.tmp/linux-probe/.venv` and OS scratch. Base/model/relay pins
are the same requirements files above. No system Python packages changed.

The optional Pascal GPU probe installs **ONNX Runtime GPU1.20.2** and private
**cuBLAS12.4.5.8, CUDA runtime12.4.127, NVRTC12.4.127, cuDNN9.3.0.75,
cuFFT11.2.1.3 and cuRAND10.3.5.147** wheels. Its complete resolved package list is
[`requirements-linux-gpu.txt`](../requirements-linux-gpu.txt), including
coloredlogs15.0.1, humanfriendly10.0, SymPy1.14.0 and mpmath1.3.0. The host NVIDIA
driver was untouched. No Torch install was needed. Compatibility choices, exact
verification and proprietary NVIDIA wheel terms are in
[`PORTABILITY.md`](PORTABILITY.md).

## Assets and notices

Public model downloads stay in ignored `models/cache`: PP-OCRv5 mobile/server,
PP-OCRv6 tiny/small/medium, and the PP-OCRv5 English-mobile recognizer. Immutable
sources, licenses and hashes are in `models/manifest.json`. Ten licensed muted
street excerpts and their originals stay in ignored `fixtures/cache`; licenses,
authors and source hashes are in `fixtures/ATTRIBUTION.md` and the manifest.
Three DejaVu font files are accompanied by `fixtures/fonts/LICENSE-DejaVu.txt`.

The copied package notices describe Linux wheels; they are not a claim that
bundled native components match every Mac wheel. Three optional ONNX dependency
notice copies were skipped after an automatic approval-review rejection. Upstream
metadata still identifies ONNX/ml_dtypes as Apache2.0 and typing_extensions as
PSF2.0. An accidentally matched, unused OpenCV plate-cascade XML was removed
from the notice snapshot; it is not a license text or a detector used here.

The raw inventory remains in ignored `out/environment/`. An all-package Homebrew
inventory encountered an unrelated untrusted Dracula cask; trust was untouched,
and the needed formula inventory used `brew list --formula --versions`.

2026-10-29 Linux static-shape support: installed ONNX 1.23.2 and ml_dtypes 0.6.0 (Apache-2.0), typing_extensions 4.16.0 (PSF-2.0) into `.tmp/linux-probe/.venv` only. Same pins as the Mac exporter; no driver or global Python changes.

## Separate merit lanes

The OpenVINO lane installed OpenVINO2026.0.0 (Apache-2.0) and the existing pinned base/model/relay requirements into its own Linux `.tmp/openvino/.venv`, under the separate `elannash/m1-openvino` worktree. No root Python or GPU environment changed. The Mac prerequisite has now installed its private SDK and completed a hash/queue-verified native CPU comparison. No main Mac venv or global Python package changed. The exact private requirements/license sources and retained installation inventory are in that lane's `bench/LOG-openvino.md` and `.tmp/openvino/installed.txt`. The queue/reporter themselves install nothing.


The FAST lane installed OnnxTR0.9.0 (Apache-2.0), ORT GPU1.20.2 and its pinned
Python stack only in its own Linux worktree `.tmp/fast/.venv`. No Mac SDK was
installed by this lane. Its complete resolved distribution inventory is below;
licenses and bundled-notice hashes for all49 distributions are retained at
`WORKTREE_t3-1b7da09d/.tmp/fast/license-inventory.json`.
The FAST34,110,202-byte weight is Apache-2.0 under the pinned model card in that
lane's manifest; source/weight hashes and runtime qualification are separate
from unmeasured all-seven privacy. These packages are not part of the root M1
runtime until the conductor reviews a separate lane PR.

```text
anyascii==0.3.3
av==16.0.1
certifi==2026.10.23
charset-normalizer==3.5.2
coloredlogs==15.0.1
colorlog==6.12.0
defusedxml==0.7.1
filelock==4.2.4
flatbuffers==25.12.19
fsspec==2026.9.0
hf-xet==1.7.1
huggingface-hub==0.36.0
humanfriendly==10.0
idna==3.20
langdetect==1.0.9
ml_dtypes==0.6.0
mpmath==1.3.0
numpy==2.2.6
nvidia-cublas-cu12==12.4.5.8
nvidia-cuda-nvrtc-cu12==12.4.127
nvidia-cuda-runtime-cu12==12.4.127
nvidia-cudnn-cu12==9.3.0.75
nvidia-cufft-cu12==11.2.1.3
nvidia-curand-cu12==10.3.5.147
omegaconf==2.4.0
onnx==1.23.2
onnxruntime-gpu==1.20.2
onnxtr==0.9.0
opencv-python-headless==4.11.0.86
packaging==26.3
pillow==11.2.1
protobuf==7.36.2
psutil==7.0.0
pyclipper==1.4.0
pypdfium2==4.30.1
pytesseract==0.3.13
PyYAML==6.0.3
RapidFuzz==3.14.3
rapidocr==3.10.0
requests==2.34.2
scipy==1.16.3
shapely==2.2.0
six==1.17.0
sympy==1.14.0
tqdm==4.70.1
typing_extensions==4.16.0
urllib3==2.8.0
```


The queued Mac OpenVINO prerequisite completed at approximately02:58UTC. It
installed the following27 distributions only in
`~/code/irl-shield-openvino/.tmp/openvino/.venv`, using the existing installer.
Exact raw inventory is retained locally at `.tmp/m1/openvino-mac-installed.txt`.
OpenVINO is Apache-2.0; other existing pins retain their original notices.

```text
av==16.0.1
certifi==2026.10.23
charset-normalizer==3.5.2
colorlog==6.12.0
flatbuffers==25.12.19
idna==3.20
ml-dtypes==0.6.0
numpy==2.2.6
omegaconf==2.4.0
onnx==1.23.2
onnxruntime==1.31.1
opencv-python-headless==4.11.0.86
openvino==2026.0.0
packaging==26.3
pillow==11.2.1
protobuf==7.36.2
psutil==7.0.0
pyclipper==1.4.0
pytesseract==0.3.13
pyyaml==6.0.3
rapidocr==3.10.0
requests==2.34.2
shapely==2.2.0
six==1.17.0
tqdm==4.70.1
typing-extensions==4.16.0
urllib3==2.8.0
```
