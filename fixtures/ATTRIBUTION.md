# Fixture attribution

Video licenses and authors were checked through Wikimedia Commons source-page
metadata on 2026-10-29. Evidence snapshots preserve the returned license fields.
Each final clip was assigned to its split before that clip was scored. The
Latin-script scope change replaced only unscored candidates; the pilot sources
remained in tune. No original is used in both splits.

Judge scope: Latin-script text. Sources are US and European street scenes,
with one Latin-script Spanish street scene from Mazatlán. The independent
judge does not establish protection for other writing systems.

Changes: fixed five-second excerpt, crop/scale to 1280×720, 30 fps, complete
audio removal, and deterministic synthetic sign overlays during benchmark runs.
No music is included in prepared clips.

| ID / split | Original and author | License |
| --- | --- | --- |
| `sf-market` / tune | [Street traffic.webm](https://commons.wikimedia.org/wiki/File:Street_traffic.webm), https://www.youtube.com/user/Editor | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0) |
| `ljubljana-walk` / tune | [Walking down the Trubarjeva street.webm](https://commons.wikimedia.org/wiki/File:Walking_down_the_Trubarjeva_street.webm), Sounds of Changes | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0) |
| `ljubljana-traffic` / tune | [Road traffic on Stritarjeva street.webm](https://commons.wikimedia.org/wiki/File:Road_traffic_on_Stritarjeva_street.webm), Sounds of Changes | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0) |
| `london-croydon` / tune | [Arriva London LJ08CXR in Addiscombe Road, Croydon (February 2016).webm](https://commons.wikimedia.org/wiki/File:Arriva_London_LJ08CXR_in_Addiscombe_Road,_Croydon_(February_2016).webm), Jontsa73 | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0) |
| `london-bus-pov` / tune | [Time Lapse - London Bus View.webm](https://commons.wikimedia.org/wiki/File:Time_Lapse_-_London_Bus_View.webm), Alessandro Massi | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0) |
| `illinois-night` / tune | [Night Views of Caton Farm Road in Crest Hill, Illinois 01.webm](https://commons.wikimedia.org/wiki/File:Night_Views_of_Caton_Farm_Road_in_Crest_Hill,_Illinois_01.webm), Illinois_Roadbuff (Rogue Jr) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0) |
| `mazatlan-aquiles` / tune | [Video de la Calle Aquiles Serdán, Mazatlán, 27 de febrero de 2019.webm](https://commons.wikimedia.org/wiki/File:Video_de_la_Calle_Aquiles_Serd%C3%A1n,_Mazatl%C3%A1n,_27_de_febrero_de_2019.webm), DogeGamer2015MZT2 | [CC0](http://creativecommons.org/publicdomain/zero/1.0/deed.en) |
| `sf-lombard` / heldout | [Lombard street (the crookedest street).webm](https://commons.wikimedia.org/wiki/File:Lombard_street_(the_crookedest_street).webm), https://www.youtube.com/user/Editor | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0) |
| `london-night` / heldout | [London Bus at night 2013-09-14 720p.ogv](https://commons.wikimedia.org/wiki/File:London_Bus_at_night_2013-09-14_720p.ogv), Brian McNeil | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0) |
| `illinois-snow` / heldout | [Snowy views of Caton Farm Rd in Crest Hill, Illinois 7.webm](https://commons.wikimedia.org/wiki/File:Snowy_views_of_Caton_Farm_Rd_in_Crest_Hill,_Illinois_7.webm), Illinois_Roadbuff (Rogue Jr) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0) |

`manifest.json` records download URLs, full original and prepared SHA-256 hashes,
source resolution, excerpt position, output dimensions, frame rate and duration.
Originals and prepared clips are generated cache files, excluded from Git.

## Fresh heldout sources

These three sources and all derived clips are **benchmark-only**, with audio
removed and no music. None is demo-ready; they must not appear in the submission
video. Full revisions, attribution requirements and modifications are recorded
in [fresh-heldout attribution](fresh-heldout/ATTRIBUTION.md) and its frozen
[manifest](fresh-heldout/manifest.json).

| ID / split | Original and author | License |
| --- | --- | --- |
| `zurich-spiegelgasse` / fresh heldout | [Spiegelgasse.ogv](https://commons.wikimedia.org/wiki/File:Spiegelgasse.ogv), [Albinfo](https://commons.wikimedia.org/wiki/User:Albinfo), own work | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |
| `chicago-wells` / fresh heldout | [New Wells Street bridge.webm](https://commons.wikimedia.org/wiki/File:New_Wells_Street_bridge.webm), [Steven Vance](https://vimeo.com/stevevance), from [Vimeo 80050981](https://vimeo.com/80050981) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) |
| `manchester-portland` / fresh heldout | [Portland Street, Manchester, May 2017.webm](https://commons.wikimedia.org/wiki/File:Portland_Street,_Manchester,_May_2017.webm), [Anders Hansson](https://vimeo.com/nders), from [Vimeo 216535229](https://vimeo.com/216535229) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) |


## Fresh heldout v2 sources

Checked on **2026-10-30 UTC** against Commons file-page revisions. These are
benchmark-only sources, never demo-ready; no logo/brand clearance is claimed.
Modifications: fixed 2–7s excerpt, 1280×720 crop/scale, zero-origin CFR30,
150 frames, complete audio/subtitle/data removal and deterministic synthetic
sign overlays. No music is included in the derived clips. Full license/revision
snapshots and recipes are in [v2 preparation](../docs/FRESH-HELDOUT-V2.md) and
[sealed selection](fresh-heldout-v2/selection.json).

| ID / split | Original and author | License |
| --- | --- | --- |
| `london-westminster` / fresh v2 heldout | [Walking in London](https://commons.wikimedia.org/w/index.php?oldid=1157657701), [POPtravel](https://www.youtube.com/channel/UClODDXeUIz1-FaKyN8dsNrA), [YouTube BgMKsDwIDgQ](https://www.youtube.com/watch?v=BgMKsDwIDgQ) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) |
| `paris-walk` / fresh v2 heldout | [Paris walking travel tour](https://commons.wikimedia.org/w/index.php?oldid=1031020312), [Le Monde en Vidéo](https://www.youtube.com/user/allairej1957), [YouTube O4W4X_UBRkg](https://www.youtube.com/watch?v=O4W4X_UBRkg) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) |
| `liverpool-walk` / fresh v2 heldout | [Walking in Liverpool](https://commons.wikimedia.org/w/index.php?oldid=1053656681), [POPtravel](https://www.youtube.com/channel/UClODDXeUIz1-FaKyN8dsNrA), [YouTube jKJ2zDSYns8](https://www.youtube.com/watch?v=jKJ2zDSYns8) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) |

## Fonts

The bundled, unmodified DejaVu Sans Bold, DejaVu Sans Mono Bold and DejaVu Serif
Bold fonts come from [DejaVu Fonts](https://dejavu-fonts.github.io/). Bitstream
Vera portions carry the Bitstream Vera font license; DejaVu changes are public
domain. The full notice is in [fonts/LICENSE-DejaVu.txt](fonts/LICENSE-DejaVu.txt).
These fonts are fixture rendering assets, separate from the video licenses.
