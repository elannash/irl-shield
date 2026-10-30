# M3 dependency and tool record

All code added under `shield/twitch/` and `tests/m3/` is original work written in
this authorized Codex thread or its authorized Codex children on 2026-10-29 PT. No other
project code, footage, music, model weights or dataset was imported. Every fixture
is synthetic Python/JSON. No detector, scorer or media bench was changed.

Runtime direct dependencies are `twitchAPI==4.5.0` ([MIT source license](https://github.com/Teekeks/pyTwitchAPI/blob/v4.5.0/LICENSE.txt))
and optional OS credential support `keyring==25.6.0`
([MIT source license](https://github.com/jaraco/keyring/blob/v25.6.0/LICENSE)).
The resolved Linux Python 3.11 package versions and distribution license metadata
are recorded in [DEPENDENCIES.json](DEPENDENCIES.json). That receipt also includes
preexisting common gate dependencies; it is an environment receipt, not a portable
lockfile. The two direct versions are pinned in [requirements.txt](requirements.txt).
No global Python installation or configuration was changed.

New transitive packages include aiohttp (Apache-2.0 AND MIT), aiohappyeyeballs
(PSF-2.0), aiosignal/frozenlist/multidict/propcache/yarl (Apache-2.0), attrs (MIT),
enum-tools (**LGPL-3.0-or-later**), python-dateutil (Apache-2.0 OR BSD-3-Clause),
Pygments (BSD-2-Clause), six (MIT), typing_extensions (PSF-2.0), tzdata (Apache-2.0),
and idna (BSD-3-Clause). Keyring transitives resolved on Linux include jaraco.classes,
jaraco.context, jaraco.functools, more-itertools, jeepney, backports.tarfile, zipp
(MIT), importlib_metadata (Apache-2.0), SecretStorage (BSD-3-Clause), cffi (MIT-0),
cryptography (Apache-2.0 OR BSD-3-Clause), and pycparser (BSD-3-Clause). Distribution
metadata and exact source/version links for each are in the JSON record. Installed
wheels retain their licenses; no dependency source is copied into project source.
If distributing a packaged binary later, retain these notices and meet the
LGPL library's redistribution/relinking requirements. M3 currently installs public
packages at setup and does not package a binary.

Twitch CLI **1.1.24** is an offline test tool, Apache-2.0, from the
[official release](https://github.com/twitchdev/twitch-cli/releases/tag/v1.1.24).
The archive carries LICENSE, NOTICE and THIRD-PARTY. Keep them next to the extracted
binary. Download the Linux x86_64 archive and checksums to the ignored `.tmp/tools/`:

```sh
curl -fL https://github.com/twitchdev/twitch-cli/releases/download/v1.1.24/twitch-cli_1.1.24_Linux_x86_64.tar.gz -o .tmp/tools/twitch-cli_1.1.24_Linux_x86_64.tar.gz
curl -fL https://github.com/twitchdev/twitch-cli/releases/download/v1.1.24/checksums.txt -o .tmp/tools/twitch-cli-checksums.txt
```

Verify the archive against the published checksum before extracting:

- Archive SHA-256: `9cae4e9cd52e66fb4dda6b633b3276a4450a28a83dea7a4651a42a67372eed8f`.
- Extracted `twitch` SHA-256: `40958ae7aed8a58f58bd9f32dec98cdd326741e5f9c1c6e6da9f7ae1df599240`.

Then `tar -xzf .tmp/tools/twitch-cli_1.1.24_Linux_x86_64.tar.gz -C .tmp/tools`.
The test verifies the binary hash before launching it. These are the executed
Linux binary's hashes; no Mac/Windows CLI compatibility is claimed.

Local installs: `.tmp/m3/venv` (initial Python 3.14 exploratory dependency download)
and `.tmp/m3/py311` (Python 3.11.14 final runtime), with task-local download/cache
directories. Python 3.11 was already installed under uv and reused read-only.
The final environment installs the repository's existing requirements and relay
requirements as well, to run the common functional checks. Archive/wheel hashes:
`/tmp/agents/irl-shield/m3-twitch/wheels.sha256`; installation output:
`/tmp/agents/irl-shield/m3-twitch/install-py311.log`. Existing common dependency
licenses remain recorded at their original introduction.

Formal checking reuses existing Java Temurin 25 and TLC 1.7.4 read-only. The
TLC jar SHA-256 is `936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88`.
The JAR's root `License.txt` is MIT; the R2 model evidence preserves that grant
separately from bundled dependency notices in `META-INF/LICENSE.txt`.
The model report in `docs/model/REPORT.md` records the exact tools, licenses,
commands, state counts and bounded claims. No model/tool installer or global
mise configuration was changed by M3.
