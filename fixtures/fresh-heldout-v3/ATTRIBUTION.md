# Fresh heldout v3 metadata and future derivatives

Benchmark-only sources. These are source metadata choices, not prepared assets
or a final dataset seal. No pixels, audio, thumbnails, OCR, inference, judging,
or human preview were used by this implementation worker. Demo use is not cleared.

The exact root-accepted selection is [selection.json](selection.json), SHA-256
`0dbb14bb2da57364c6b1ca131c29619e9270297298abb4222aa277d633c5f1df`.
Root's acceptance is [ACCEPTANCE.json](ACCEPTANCE.json), SHA-256
`efe5742366d6fc5f240f43beb68212a61e91f960614cfa7748946a8b9141b02e`.
Those original bytes and their relative provenance references are preserved.

| Source | Creator credited by Commons | License | Immutable description revision |
| --- | --- | --- | --- |
| [Ryde, Somerset Road](https://commons.wikimedia.org/wiki/File:%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D1%8F_-_%D0%BF%D0%BE%D1%87%D1%82%D0%BE%D0%B2%D0%BE%D0%B5_%D0%BE%D1%82%D0%B4%D0%B5%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5.ogv) | Жизнь на юге Англии | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | [1189685130](https://commons.wikimedia.org/w/index.php?oldid=1189685130) |
| [Recall Election Day — Madison, WI](https://commons.wikimedia.org/wiki/File:Recall_Election_Day_-_Madison,_WI.webm) | teaching kristin | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | [1031922187](https://commons.wikimedia.org/w/index.php?oldid=1031922187) |
| [Walking across the footbridge in Katowice, 20240808](https://commons.wikimedia.org/wiki/File:Walking_across_the_footbridge_in_Katowice,_20240808.webm) | User:Abzeronow | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | [1261664289](https://commons.wikimedia.org/w/index.php?oldid=1261664289) |

Creator names and original titles retain their source spelling for attribution.
The three [source extracts](sources) bind the exact author, license, original
URL, byte count, SHA1, origin work, and revision. The [raw response](raw/selected-three-verification.json)
pins the API's template expansion; the [HTTP receipt](raw/selected-three-verification.receipt.json)
contains relative paths only. The receipt is copied byte for byte: its SHA-256
is recorded in [metadata-contract.json](metadata-contract.json). No public
owner filesystem path is introduced by these metadata files.

Future changes to each original: use only file-relative seconds 2–7, resize
with aspect-ratio increase and center crop to 1280×720, set CFR30/start0 and
exactly 150 frames, encode CPU libx264 medium 10M yuv420p, remove all audio,
subtitles, data, source metadata and chapters. The synthetic variant adds the
project's deterministic fictional signs with the unchanged v2 camera-tracking
algorithm and fixed v3 seeds. These derivative operations have not run yet.
Existing project dependencies and bundled DejaVu font licensing are unchanged.

Original SHA-256s and every derived hash remain unknown until root physically
prepares the dataset. Madison advertises 7.712 seconds; the fixed 2–7 second
excerpt must yield 150 actual frames or preparation stops. No replacement or
alternate excerpt is authorized. Natural truth contains 150 empty synthetic
truth arrays; it makes no claim about natural text visible in the video.

The final manifest is created only by a future root `freeze` after all three
originals, six videos, six truth files and per-clip receipts verify. It must
remain frozen-ungraded with at most one evaluation, not before
`2026-11-02T12:00:00Z`, and `evaluation_started: false`. The conductor owns that
one-shot. The metadata source seal alone does not release new tuning output.
