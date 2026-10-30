# Claims and evidence ledger

Snapshot at parent `65891cb0b515bc0c34ec4ded89aa6a3228992cc2`. These are drafting anchors, not new qualification results. Root must update this ledger with final integrated evidence before publication.

| Proposed claim | Source | What can be said now |
|---|---|---|
| Delayed frame clock and asynchronous detection | `shield/engine.py` `MaskingEngine.submit`, `_coverage_and_quads`, `poll`; `docs/ARCHITECTURE.md` | Implemented architecture. No guarantee that every clue is found in time. |
| Pixels masked before egress | `relay/live.py` `RelaySession.tick`; `relay/stream.py` writer path; `shield/render.py` | A downstream recording of the emitted pixels retains masks that were actually applied. No universal claim about missed clues, raw phone recordings or alternate bypass routes. |
| Chat/Shield holds are independent | `docs/RUN.md` EventSub controls; `shield/control.py`; `shield/twitch/events.py` | Implemented policy. Live demonstration still needs attended evidence. |
| Independent truth, all-judge output leak checks | `bench/README.md` Fixtures, scope and truth; `bench/metrics.py`; `tests/test_judge_independence.py` | Explain methodology. Natural target remains not passed. A valid output judge can expose a leak; this is not proof against every reader or clue. |
| Protocol-based app support | `README.md` frame engine; `docs/RUN.md` ingest setup | Transport-independent engine. State only tested app/protocol combinations as qualified. SRT acceptance pending. |
| Twitch forwarder acceptance | Parent task status supplied to W10 | Verified forwarder's real Twitch `tcUrl` acceptance still needs attended test. Local mocks do not prove it. |
| Built with Codex | `AGENTS.md` Roles and Hackathon rules; exact source history to be supplied by owner | All new W10 code originates in this Codex child. Real build-session extraction and replay have not been performed in W10. |
| Privacy/performance metrics | Final reviewed scorecard required | None measured here. All metric fields in W10 handback are null. |

Do not claim perfect privacy, universal app qualification, lack of Moblin privacy controls, or clip safety against undetected clues. Automatic coverage is the product goal. Moderator actions provide complementary controls.

## Official submission facts

Checked 2026-10-30 against [Official Rules](https://twitchcon-codex.devpost.com/rules), sections 1 and 4. The deadline is Nov 2 at 2 PM Pacific. A repository, project description, Codex session ID and public YouTube demonstration are required. Keep the video under three minutes and show Twitch functionality and the Codex build process. The project must run as described and be free for judges. Rights to included material must be cleared. Materials are in English.

The organizer's [Resources FAQ](https://twitchcon-codex.devpost.com/resources) has an inconsistent UTC conversion. Use the official rules' Pacific deadline, not that conversion. No timezone conversion in this package authorizes a later deadline.

[Official OpenAI non-interactive guide](https://developers.openai.com/codex/noninteractive/) and [CLI reference](https://developers.openai.com/codex/cli/reference) document stdin prompts, read-only execution, ephemeral sessions and JSON events. The installed `codex exec --help` confirms those flags plus `--ignore-user-config`. Documentation/help retrieval was read-only and made no model request. A read-only command sandbox is not proof of filesystem read isolation or a ban on tools.
