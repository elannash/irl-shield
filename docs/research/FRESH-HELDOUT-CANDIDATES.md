# Fresh held-out footage candidates — benchmark only

Prepared on **2026-10-30 UTC**, from public Wikimedia Commons metadata. This is
research for the conductor; **nothing is downloaded, frozen, or graded by this
child**. Q remains held until PR4 merges. The conductor owns final selection,
downloads, excerpt preparation, synthetic truth, policy freeze, and the one
subsequent held-out grading run. These are **benchmark-only candidates**, not
approved submission-video assets.

Recommend exactly three preferred originals: Zürich Spiegelgasse, Chicago Wells
Street bridge, and Manchester Portland Street. Each is a different source,
author, and city. One backup is supplied: Seattle's Alaskan Way Viaduct timelapse.
All four Commons originals are at least 1280×720 and below 200,000,000 bytes;
original dimensions are used, not the page's smaller preview dimensions.
The original capture resolution and absence of earlier upscaling are not
independently established by container metadata. No benchmark upscaling is
proposed.

The geographic/script match is an inference from the documented US/European
locations. No claim is made that a particular excerpt contains readable Latin
text, plates, storefronts, or a particular camera pan: no video, thumbnail,
image, decoded frame, OCR result, detector, judge, old scorecard, or held-out grade
was inspected. All original and derived SHA-256 values remain unknown until
actual bytes are fetched. The advertised Commons SHA-1 values below are metadata,
not hashes this child computed from media.

## Preferred set and backup

All page, API, and original-URL HEAD accesses were on **2026-10-30 UTC**. Duration
and byte counts are the Commons `imageinfo` fields, preserved with file-page
wikitext in the evidence paths below. HTTP HEAD checks read no response body.

| Priority / proposed ID | Source and author | License explicitly on file page | Original dimensions | Original duration | Original bytes | Fixed excerpt |
| --- | --- | --- | --- | --- | --- | --- |
| Preferred 1 / `zurich-spiegelgasse` | [Spiegelgasse.ogv][zurich], [Albinfo](https://commons.wikimedia.org/wiki/User:Albinfo), own work | [CC0 1.0 Universal][cc0] | 1920×1080 | 120.30494341870161 s | 77,497,684 | 2.000–7.000 s |
| Preferred 2 / `chicago-wells` | [New Wells Street bridge.webm][chicago], [Steven Vance](https://vimeo.com/stevevance) | [CC BY 3.0 Unported][by3] | 1280×720 | 53.987 s | 28,086,878 | 2.000–7.000 s |
| Preferred 3 / `manchester-portland` | [Portland Street, Manchester, May 2017.webm][manchester], [Anders Hansson](https://vimeo.com/nders) | [CC BY 3.0 Unported][by3] | 1920×1080 | 12.44 s | 20,955,496 | 2.000–7.000 s |
| Backup / `seattle-viaduct` | [Alaskan Way Viaduct timelapse.webm][seattle], [jonknee](https://www.youtube.com/user/jonknee) | [CC BY 3.0 Unported][by3] | 1920×1080 | 19.048 s | 23,280,459 | 2.000–7.000 s |

Zürich is the strongest walking match: its page describes a walk through the old
town and categorizes it as first-person footage on foot. This is the uploader's
own CC0 work. [File page, Summary and Licensing][zurich].

Chicago adds a moving handlebar viewpoint on a city street bridge, explicitly
described in the file metadata. Its page records Vimeo source
[80050981](https://vimeo.com/80050981) and a successful license review dated
2019-12-09. Street and vehicle text are plausible, but their actual presence in
the fixed interval is unverified. [File-page revision][chicago-rev].

Manchester adds a distinct UK city and author. Its page documents Portland Street,
coordinates, the Vimeo source [216535229](https://vimeo.com/216535229), and a
successful license review by Explicit dated 2017-12-11. The page also links a
second Manchester bus file; that second file is **not** proposed here. Camera
motion and visible text in the chosen interval remain unverified.
[File page, Summary and Licensing][manchester].

Seattle is a usable metadata/license backup, but its documented northbound
freeway drive is a **timelapse**, so it is a weaker match for normal walking
motion. Its page records the YouTube source
[DMIir2J0rsE](https://www.youtube.com/watch?v=DMIir2J0rsE) and a successful license
review dated 2020-02-13. Do not substitute it after seeing held-out scores.
[File page, Summary and Licensing][seattle].

The excerpt rule is fixed before any image inspection: start **2.000 seconds**
into each Commons original and take **5.000 seconds**. Every source's metadata
provides at least seven seconds. This leaves two seconds at the beginning and
at least five seconds at the end of even the shortest file; it does not
establish that introductions or cuts are absent. Offsets did not use detector
or judge feedback.

## Exact originals and advertised SHA-1

These are upload.wikimedia.org **original-file** URLs, with the API's optional
`utm_*` tracking query removed. Each returned HTTP 200 to a HEAD request, with
`Content-Length` equal to the byte count above. No GET of media was made.

| ID | Direct original URL | Commons-advertised SHA-1 |
| --- | --- | --- |
| `zurich-spiegelgasse` | [Spiegelgasse.ogv](https://upload.wikimedia.org/wikipedia/commons/5/56/Spiegelgasse.ogv) | `b2336d66df6947e452a5289dfa0d36d6937b5e7c` |
| `chicago-wells` | [New_Wells_Street_bridge.webm](https://upload.wikimedia.org/wikipedia/commons/d/d3/New_Wells_Street_bridge.webm) | `f0391066bec82f53e7ceedba757563b93aa6966c` |
| `manchester-portland` | [Portland_Street%2C_Manchester%2C_May_2017.webm](https://upload.wikimedia.org/wikipedia/commons/e/eb/Portland_Street%2C_Manchester%2C_May_2017.webm) | `d5c4042f900a765ec87d4c66a14747a9d36faaaf` |
| `seattle-viaduct` | [Alaskan_Way_Viaduct_timelapse.webm](https://upload.wikimedia.org/wikipedia/commons/7/78/Alaskan_Way_Viaduct_timelapse.webm) | `6ef73fbc8ed316c8bbb2375b80d9fcd0259759f6` |

The machine-readable block below is part of this research report. `null` means
**not downloaded and not hash-verified**, not a missing value to fill by guesswork.
The root recipe reads this exact block, selects only the three preferred items,
and checks the original byte counts and SHA-1 before calculating SHA-256.

<!-- fresh-heldout-metadata:start -->
```json
{
  "status": "research-only-unfrozen",
  "base_head": "f2f57892b731949d17ce62ba4dcd84d74fb26ab0",
  "candidates": [
    {
      "id": "zurich-spiegelgasse",
      "title": "File:Spiegelgasse.ogv",
      "source_url": "https://commons.wikimedia.org/wiki/File:Spiegelgasse.ogv",
      "revision_url": "https://commons.wikimedia.org/w/index.php?title=File:Spiegelgasse.ogv&oldid=950417958",
      "revision_id": 950417958,
      "download_url": "https://upload.wikimedia.org/wikipedia/commons/5/56/Spiegelgasse.ogv",
      "author": "Albinfo",
      "license": "CC0",
      "license_url": "http://creativecommons.org/publicdomain/zero/1.0/deed.en",
      "source_width": 1920,
      "source_height": 1080,
      "source_duration_seconds": 120.30494341870161,
      "source_size_bytes": 77497684,
      "source_sha1": "b2336d66df6947e452a5289dfa0d36d6937b5e7c",
      "excerpt_start": 2.0,
      "excerpt_seconds": 5.0,
      "access_date_utc": "2026-10-30",
      "role": "preferred",
      "source_sha256": null
    },
    {
      "id": "chicago-wells",
      "title": "File:New Wells Street bridge.webm",
      "source_url": "https://commons.wikimedia.org/wiki/File:New_Wells_Street_bridge.webm",
      "revision_url": "https://commons.wikimedia.org/w/index.php?title=File:New_Wells_Street_bridge.webm&oldid=1138938708",
      "revision_id": 1138938708,
      "download_url": "https://upload.wikimedia.org/wikipedia/commons/d/d3/New_Wells_Street_bridge.webm",
      "author": "Steven Vance",
      "license": "CC BY 3.0",
      "license_url": "https://creativecommons.org/licenses/by/3.0",
      "source_width": 1280,
      "source_height": 720,
      "source_duration_seconds": 53.987,
      "source_size_bytes": 28086878,
      "source_sha1": "f0391066bec82f53e7ceedba757563b93aa6966c",
      "excerpt_start": 2.0,
      "excerpt_seconds": 5.0,
      "access_date_utc": "2026-10-30",
      "role": "preferred",
      "source_sha256": null
    },
    {
      "id": "manchester-portland",
      "title": "File:Portland Street, Manchester, May 2017.webm",
      "source_url": "https://commons.wikimedia.org/wiki/File:Portland_Street,_Manchester,_May_2017.webm",
      "revision_url": "https://commons.wikimedia.org/w/index.php?title=File:Portland_Street%2C_Manchester%2C_May_2017.webm&oldid=1029110982",
      "revision_id": 1029110982,
      "download_url": "https://upload.wikimedia.org/wikipedia/commons/e/eb/Portland_Street%2C_Manchester%2C_May_2017.webm",
      "author": "Anders Hansson",
      "license": "CC BY 3.0",
      "license_url": "https://creativecommons.org/licenses/by/3.0",
      "source_width": 1920,
      "source_height": 1080,
      "source_duration_seconds": 12.44,
      "source_size_bytes": 20955496,
      "source_sha1": "d5c4042f900a765ec87d4c66a14747a9d36faaaf",
      "excerpt_start": 2.0,
      "excerpt_seconds": 5.0,
      "access_date_utc": "2026-10-30",
      "role": "preferred",
      "source_sha256": null
    },
    {
      "id": "seattle-viaduct",
      "title": "File:Alaskan Way Viaduct timelapse.webm",
      "source_url": "https://commons.wikimedia.org/wiki/File:Alaskan_Way_Viaduct_timelapse.webm",
      "revision_url": "https://commons.wikimedia.org/w/index.php?title=File:Alaskan_Way_Viaduct_timelapse.webm&oldid=1036413182",
      "revision_id": 1036413182,
      "download_url": "https://upload.wikimedia.org/wikipedia/commons/7/78/Alaskan_Way_Viaduct_timelapse.webm",
      "author": "jonknee",
      "license": "CC BY 3.0",
      "license_url": "https://creativecommons.org/licenses/by/3.0",
      "source_width": 1920,
      "source_height": 1080,
      "source_duration_seconds": 19.048000000000002,
      "source_size_bytes": 23280459,
      "source_sha1": "6ef73fbc8ed316c8bbb2375b80d9fcd0259759f6",
      "excerpt_start": 2.0,
      "excerpt_seconds": 5.0,
      "access_date_utc": "2026-10-30",
      "role": "backup",
      "source_sha256": null
    }
  ]
}
```
<!-- fresh-heldout-metadata:end -->

## Nonreuse and evidence

The exclusion frame was exactly **all ten entries**, including tune and held-out,
in [`fixtures/manifest.json`](../../fixtures/manifest.json), cross-checked against
[`fixtures/ATTRIBUTION.md`](../../fixtures/ATTRIBUTION.md), at base
`f2f57892b731949d17ce62ba4dcd84d74fb26ab0`. No grade or scorecard was opened.
Excluded titles were:

- `Street traffic.webm`
- `Walking down the Trubarjeva street.webm`
- `Road traffic on Stritarjeva street.webm`
- `Arriva London LJ08CXR in Addiscombe Road, Croydon (February 2016).webm`
- `Time Lapse - London Bus View.webm`
- `Night Views of Caton Farm Road in Crest Hill, Illinois 01.webm`
- `Video de la Calle Aquiles Serdán, Mazatlán, 27 de febrero de 2019.webm`
- `Lombard street (the crookedest street).webm`
- `London Bus at night 2013-09-14 720p.ogv`
- `Snowy views of Caton Farm Rd in Crest Hill, Illinois 7.webm`

None of the four proposed titles, normalized source-page URLs, normalized original
URLs, or advertised original SHA-1 values matches an existing entry. The four
candidates' advertised SHA-1 values also differ from each other. This establishes
nonreuse against those two input files, not against unknown future conductor
selections or an unseen copy of the same recording uploaded elsewhere.

Research receipts are retained in this child's locked worktree,
`/home/elan/.t3/worktrees/irl-shield/t3-07121fdd` (paths below are relative to
that worktree, not the conductor's checkout):

- `.tmp/heldout-prep/final-batch.api.json`: public API request URL, UTC access
  timestamp, original metadata, license fields, author, and complete file-page
  wikitext/revision IDs for all four candidates.
- `.tmp/heldout-prep/<id>.verified-api.json` and `<id>.file-page.wikitext`:
  per-candidate extracts, with the original returned text preserved as data.
- `.tmp/heldout-prep/original-url-head.json`: all HEAD attempts, including
  successful 200/length checks for every candidate; `media_body_read: false`.
- `.tmp/heldout-prep/nonreuse.json`: the input-file SHA-256 values, ten-source
  exclusion list, and empty match sets for all four candidates.
- `.tmp/heldout-prep/candidates.json`: normalized metadata extraction.
- `.tmp/heldout-prep/evidence.sha256`: hashes of the retained relevant evidence.

An expanded API batch initially hit HTTP 429; the later batched retry succeeded.
A Manchester HEAD request also hit 429 with `Retry-After: 1`; after waiting at
least that interval, it returned 200. No access/permission bypass was used.
The web reader could not open the Chicago page; its live Commons API response
and exact [page revision][chicago-rev] supply the license evidence instead.
CC BY-SA-only sources and uncertain-location stock clips were not selected.
No model, executable dataset, or dependency was introduced.

## Conductor follow-up commands — not executed by this child

Run from the root's intended checkout **only after conductor authorization for
media preparation**, using existing Python 3.11+, ffmpeg, and ffprobe. There are
no package installations, Mac calls, GPU operations, OCR, detector, judge, or
bench invocations below. The recipe makes an isolated candidate cache and does
not edit the existing fixture manifest or attribution file. It deliberately
refuses to overwrite an existing cache directory.

This first block performs actual downloads, verifies advertised size/SHA-1,
computes real SHA-256 values, probes container metadata, and prepares exactly
the three fixed excerpts with a local CPU encoder. It strips all audio, subtitle,
data streams and metadata; output is 1280×720 at 30 fps. It does not render stills
or grade frames. These operations remain the root's work, subject to the hold.
The root must capture command output and encoder/tool versions with its receipts.

```bash
python3 - <<'PYROOT'
from pathlib import Path
from fractions import Fraction
import hashlib, json, re, subprocess, urllib.parse, urllib.request

report = Path('docs/research/FRESH-HELDOUT-CANDIDATES.md').read_text()
match = re.search(r'<!-- fresh-heldout-metadata:start -->\s*```json\n(.*?)\n```', report, re.S)
if match is None:
    raise RuntimeError('Research metadata block missing')
plan = json.loads(match.group(1))
clips = [c for c in plan['candidates'] if c['role'] == 'preferred']
assert len(clips) == 3
existing = json.loads(Path('fixtures/manifest.json').read_text())['clips']
def normalized(value):
    return urllib.parse.unquote(value).replace('_', ' ')
for clip in clips:
    assert clip['license'] in ('CC0', 'CC BY 3.0', 'CC BY 4.0', 'Public domain')
    assert clip['source_width'] >= 1280 and clip['source_height'] >= 720
    assert clip['excerpt_start'] == 2.0 and clip['excerpt_seconds'] == 5.0
    for old in existing:
        for key in ('source_url', 'download_url', 'source_sha1'):
            assert normalized(clip[key]) != normalized(old[key]), (clip['id'], old['id'], key)
base = Path('fixtures/cache/fresh-heldout-q')
base.mkdir(parents=True, exist_ok=False)
(base / 'research-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
for tool in ('ffmpeg', 'ffprobe'):
    (base / (tool + '-version.txt')).write_text(subprocess.check_output([tool, '-version'], text=True))
def digest(path, algorithm):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()
def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)
    ], text=True))
for clip in clips:
    suffix = Path(urllib.parse.urlsplit(clip['download_url']).path).suffix
    original = base / (clip['id'] + suffix)
    request = urllib.request.Request(clip['download_url'], headers={
        'User-Agent': 'IRLShieldBench/1.0 (licensed public benchmark source preparation)'
    })
    # HTTP errors stop this run; honor any Retry-After before a later authorized retry.
    with urllib.request.urlopen(request, timeout=120) as response, original.open('xb') as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    assert original.stat().st_size == clip['source_size_bytes'], clip['id']
    assert digest(original, 'sha1') == clip['source_sha1'], clip['id']
    clip['source_sha256'] = digest(original, 'sha256')
    assert clip['source_sha256'] not in {c['source_sha256'] for c in existing}
    original_probe = probe(original)
    (base / (clip['id'] + '.original.ffprobe.json')).write_text(json.dumps(original_probe, indent=2) + '\n')
    video = next(s for s in original_probe['streams'] if s['codec_type'] == 'video')
    assert (video['width'], video['height']) == (clip['source_width'], clip['source_height'])
    assert float(original_probe['format']['duration']) >= clip['excerpt_start'] + clip['excerpt_seconds']
    output = base / (clip['id'] + '.excerpt.mp4')
    subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-n', '-ss', '2.000', '-i', str(original),
        '-map', '0:v:0', '-an', '-sn', '-dn', '-t', '5.000',
        '-vf', 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30,setsar=1',
        '-c:v', 'libx264', '-preset', 'medium', '-b:v', '10M', '-pix_fmt', 'yuv420p',
        '-map_metadata', '-1', '-map_chapters', '-1', '-movflags', '+faststart', str(output)
    ], check=True)
    output_probe = probe(output)
    (base / (clip['id'] + '.excerpt.ffprobe.json')).write_text(json.dumps(output_probe, indent=2) + '\n')
    streams = output_probe['streams']
    assert len(streams) == 1 and streams[0]['codec_type'] == 'video'
    video = streams[0]
    assert (video['width'], video['height'], Fraction(video['avg_frame_rate'])) == (1280, 720, Fraction(30))
    assert int(video['nb_frames']) == 150
    assert abs(float(output_probe['format']['duration']) - 5.0) <= 1/30
    clip.update({'split': 'heldout', 'source_path': str(original), 'path': str(output),
                 'sha256': digest(output, 'sha256'), 'width': 1280, 'height': 720,
                 'fps': 30, 'duration': 5.0, 'encoder': 'libx264', 'audio': 'removed'})
assert len({c['source_sha256'] for c in clips}) == 3
receipt = {'status': 'prepared-unfrozen-ungraded', 'clips': clips,
           'report_sha256': digest(Path('docs/research/FRESH-HELDOUT-CANDIDATES.md'), 'sha256')}
(base / 'prepared.json').write_text(json.dumps(receipt, indent=2) + '\n')
with (base / 'media.sha256').open('x') as output:
    for clip in clips:
        for key in ('source_path', 'path'):
            path = Path(clip[key])
            output.write(f"{digest(path, 'sha256')}  {path}\n")
print('Prepared only; no held-out evaluation or policy freeze performed:', base / 'prepared.json')
PYROOT
sha256sum --check fixtures/cache/fresh-heldout-q/media.sha256
```

The `libx264` CPU recipe is a proposed standalone preparation recipe. It is not
the current fixture preparer's canonical NVENC output. The root must retain
encoder/recipe provenance if it adopts these outputs. The existing
[`fixtures/prepare.py`](../../fixtures/prepare.py) requires a frozen allocation
of seven tune and three held-out clips and reads only the existing manifest;
blindly adding these three entries or invoking `scripts/bench` is not a valid
integration or freeze procedure. The conductor must review how fresh held-outs
replace or sit beside the old allocation, add attribution, and assign synthetic
truth/seeds before any grading. None of that integration is done here.

The next block is a separate, local freeze receipt. Run it **only after the
conductor identifies the final Q policy commit and completes synthetic truth
and allocation preparation**. Its `git rev-parse HEAD` must name that final,
committed policy revision; a dirty checkout makes it stop. It binds the
prepared clips and the conductor's reviewed truth to that revision but does
not invoke a detector/judge or count as the single grading run. The conductor
must first supply `fixtures/cache/fresh-heldout-q/truth-and-allocation.json`,
containing the reviewed truth/seed recipe and exactly these three clip IDs.

```bash
python3 - <<'PYROOT'
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, subprocess
base = Path('fixtures/cache/fresh-heldout-q')
if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], text=True):
    raise RuntimeError('Freeze requires a clean final-policy checkout')
policy_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
prepared_path = base / 'prepared.json'
prepared = json.loads(prepared_path.read_text())
assert prepared['status'] == 'prepared-unfrozen-ungraded'
truth_path = base / 'truth-and-allocation.json'
truth = json.loads(truth_path.read_text())
assert sorted(truth['clip_ids']) == sorted(c['id'] for c in prepared['clips'])
subprocess.run(['sha256sum', '--check', str(base / 'media.sha256')], check=True)
frozen = {'status': 'frozen-ungraded', 'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
          'q_policy_commit': policy_commit, 'prepared_receipt_sha256': digest(prepared_path),
          'truth_and_allocation_sha256': digest(truth_path), 'clips': prepared['clips'],
          'media_hash_manifest_sha256': digest(base / 'media.sha256')}
with (base / 'frozen.json').open('x') as output:
    output.write(json.dumps(frozen, indent=2) + '\n')
print('Frozen receipt only; conductor still owns the single subsequent held-out grading run.')
PYROOT
sha256sum fixtures/cache/fresh-heldout-q/frozen.json
```

These command blocks were syntax-checked locally as text, **not executed against
media**. The root still has to run and verify its authorized preparation.
A content failure discovered during a permitted pre-score review must be
recorded before grading, without looking at held-out detector/judge outcomes.
No substitution based on scores, repeated held-out tuning, or demo-readiness
claim is authorized by this research report. Audio removal does not establish
visual rights clearance or absence of readable third-party brands/logos.

[zurich]: https://commons.wikimedia.org/wiki/File:Spiegelgasse.ogv
[chicago]: https://commons.wikimedia.org/wiki/File:New_Wells_Street_bridge.webm
[manchester]: https://commons.wikimedia.org/wiki/File:Portland_Street,_Manchester,_May_2017.webm
[seattle]: https://commons.wikimedia.org/wiki/File:Alaskan_Way_Viaduct_timelapse.webm
[chicago-rev]: https://commons.wikimedia.org/w/index.php?title=File:New_Wells_Street_bridge.webm&oldid=1138938708
[cc0]: https://creativecommons.org/publicdomain/zero/1.0/
[by3]: https://creativecommons.org/licenses/by/3.0/
