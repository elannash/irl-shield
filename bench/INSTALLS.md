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
