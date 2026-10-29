# License receipts

`PaddleOCR-APACHE-2.0.txt` comes from the
[PaddleOCR license](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE).
`RapidOCR-APACHE-2.0.txt` comes from the
[RapidOCR v3.10.0 license](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/LICENSE).
`RapidOCR-MODEL_LICENSES.md` is the model notice distributed inside the
RapidOCR 3.10.0 Python wheel. Model-specific source revisions, license cards,
artifact URLs, and SHA-256 pins are in `../manifest.json`.

`dependencies.json` records each locked runtime distribution's package
metadata and copied license/notice paths. The snapshots were collected from
the Linux CPython 3.11 installation of `requirements-models.txt` on
2026-10-29. The flatbuffers wheel contains no license file, so its Apache-2.0
text was retrieved from its
[matching upstream release](https://github.com/google/flatbuffers/blob/v25.12.19/LICENSE).
Other snapshots come directly from the installed distribution's license or
notice files, retaining their relative paths to avoid filename collisions.

These receipts distinguish top-level package licenses from bundled native
components and their notices. They do not replace the terms in those texts.
Native dependencies can differ across platform wheels; retain the macOS
wheel notices as well when distributing a macOS binary.
