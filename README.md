# IRL Shield

IRL Shield covers readable text on street signs, storefronts, house numbers and plates before an IRL stream reaches Twitch. It runs as a relay between the streamer's phone and Twitch. Chat and moderators can vote on how masks look and can hold the stream on a privacy slate.

Demo video: https://youtu.be/DIRiN-hniaI

3rd place of 501 projects (2,217 participants), [Codex x TwitchCon Hackathon](https://devpost.com/software/irl-shield), Nov 2026. The judged version is the git tag [`submission`](https://github.com/elannash/irl-shield/tree/submission).

No longer maintained. MIT-licensed; forks and reuse welcome.

![Generated storefront scene, before on the left and shielded with Patch on the right](docs/images/generated-before-after.png)

The image shows a generated scene with fictional names, before (left) and shielded with Patch (right).

## How it works

- Moblin on the phone sends RTMP over Tailscale to the Linux relay.
- On GPU, the relay holds video in a 1-second processing buffer by default. Total delay to viewers has not been measured.
- PP-OCRv5-mobile detectors find text to mask. They miss some text, mainly small or distant text.
- Masks cover detected text. Frames the detectors have not checked go out protected.
- NVENC encodes the video on GPU (libx264 with `--cpu`). A TLS forwarder sends it to Twitch and verifies Twitch's certificate.
- In chat, moderators and the broadcaster can put the stream on a privacy slate with `!shield hold`, and viewers vote on the mask style with `!skin bar` or `!skin patch`. A phone dashboard has the same Hold control. See [dashboard details](docs/DASHBOARD.md) and [skin controls](docs/SKINS.md#chat-voting).

To install and run it, follow [docs/RUN.md](docs/RUN.md). It needs Linux x86-64 and Python 3.11, and an NVIDIA GPU is recommended. A local mode runs without Twitch credentials and publishes nothing.

## Limitations

- The detectors miss some text, so a sign can still reach viewers. Use Hold before a known location clue enters the frame.
- It covers text only. Landmarks and other visual location clues stay visible.
- Hold stops further exposure. It cannot take back frames already sent.
- Live Twitch publishing is restricted to the original broadcaster account, `naie`. Bandwidth-test mode works with your own Twitch app; see [Twitch authorization and controls](docs/RUN.md#twitch-authorization-and-controls).
- This is an experimental relay, not a production service. The [architecture notes](docs/ARCHITECTURE.md) and [held-out evaluation](docs/Q-FRESH-HELDOUT-RESULT.md) record what was and was not measured.

Some historical docs use path placeholders such as `REPO_ROOT` and `OWNER_HOME`. Replace them with local paths before running a command from them.

## Built with Codex

One OpenAI Codex thread and its Codex subagents wrote the code during the hackathon. Claude Opus planned and reviewed the work.

## License

The code is under the [MIT License](LICENSE). Bundled third-party files keep their own licenses:

- DejaVu fonts in `fixtures/fonts`, under the Bitstream Vera license ([notice](fixtures/fonts/LICENSE-DejaVu.txt)).
- Atkinson Hyperlegible Next in `shield/presentation/assets`, under the SIL Open Font License 1.1 ([notice](shield/presentation/assets/OFL.txt)).
- The qrcode library notice in [`shield/dashboard/licenses`](shield/dashboard/licenses/qrcode-LICENSE).
- Model and dependency notices in [`models/licenses`](models/licenses/README.md). Model files download at setup; [models/manifest.json](models/manifest.json) lists their sources, hashes and licenses.

Fixture footage and images are listed with their sources and licenses in [fixtures/ATTRIBUTION.md](fixtures/ATTRIBUTION.md).
