# Fresh heldout benchmark footage

All originals, excerpts, synthetic variants, masked outputs and any previews
are **benchmark-only**. None is demo-ready. Street scenes can contain readable
third-party names and logos. All derived videos remove audio; no music is used.
Do not use these assets in the submission video.

The three sources were chosen from Commons metadata before viewing pixels or
scores. Every excerpt is fixed at 2.000–7.000 seconds. The metadata-only backup
was not substituted. The source downloads were verified against the byte counts
and SHA-1 values in Commons' imageinfo response; actual SHA-256 values, author
HTML, original URLs and revision IDs are frozen in `manifest.json`. That manifest
also preserves the public API response's relevant pages and revision wikitext.

| Clip ID | Original and author | License | Preserved file-page revision |
| --- | --- | --- | --- |
| `zurich-spiegelgasse` | [Spiegelgasse.ogv](https://commons.wikimedia.org/wiki/File:Spiegelgasse.ogv), [Albinfo](https://commons.wikimedia.org/wiki/User:Albinfo), own work | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | [950417958](https://commons.wikimedia.org/w/index.php?oldid=950417958) |
| `chicago-wells` | [New Wells Street bridge.webm](https://commons.wikimedia.org/wiki/File:New_Wells_Street_bridge.webm), [Steven Vance](https://vimeo.com/stevevance), from [Vimeo 80050981](https://vimeo.com/80050981) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | [1138938708](https://commons.wikimedia.org/w/index.php?oldid=1138938708) |
| `manchester-portland` | [Portland Street, Manchester, May 2017.webm](https://commons.wikimedia.org/wiki/File:Portland_Street,_Manchester,_May_2017.webm), [Anders Hansson](https://vimeo.com/nders), from [Vimeo 216535229](https://vimeo.com/216535229) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | [1029110982](https://commons.wikimedia.org/w/index.php?oldid=1029110982) |

Changes: excerpting; scaling/cropping to 1280×720; conversion to CFR 30fps,
H.264/NVENC p4 at 10M, yuv420p; removal of audio and source metadata; and a
separate synthetic variant adding project-authored location labels. Retain
this attribution and the license links when sharing the CC BY derivatives.
No endorsement by the original authors is implied.

The labels are made by the existing `bench.synthetic.overlay` API, using the
same DejaVu font files, text/style inventory, positions and camera tracking
recipe as tune. Font terms remain in [the existing attribution](../ATTRIBUTION.md)
and `fixtures/fonts/LICENSE-DejaVu.txt`. Existing NumPy, OpenCV, Pillow,
FFmpeg/NVENC dependencies are reused under their already recorded terms; no
package, model or service is added. FFmpeg terms: <https://ffmpeg.org/legal.html>.

Original authorship and scene descriptions are source-page claims. No visual
inspection or OCR was performed to establish content suitability, brand
absence, natural-text density or real-world privacy coverage. Container and
frame-accounting checks establish technical validity only.
