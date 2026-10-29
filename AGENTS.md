# AGENTS.md

IRL Shield sits between an IRL streamer's phone and Twitch and hides readable
location text (street signs, storefronts, plates, house numbers) before the
video reaches viewers. Entry for the Codex x TwitchCon hackathon; submissions
close Mon Nov 2 2026, 2:00 PM PT.

This file adds to `~/.agents/AGENTS.md` and wins where they conflict.

## Roles

- Claude Opus 5.5 conducts: writes packets, reviews hand-backs, commits,
  opens and merges PRs.
- One Codex thread (GPT-6.1 Sol) writes the code and may spawn Codex
  subagents. Its session ID is the one submitted, so the code is written in
  that thread or its Codex children.

## Machines

- The repo lives on elan-linux. Apple Vision, Core Image and VideoToolbox
  exist only on the MacBook Pro (M1 Pro, macOS 27, Xcode 27): build, run and
  bench there over `ssh mac` (use `bash -lc` for the login PATH).
- The phone reaches the Mac over Tailscale. The Mac's ffmpeg has RTMP and
  `h264_videotoolbox`, no SRT.

## The bench is the acceptance signal

- `bench` scores the pipeline on licensed fixtures and writes a scorecard.
  Every change to detection, masking, scheduling or the stream path reruns
  it and quotes the scorecard in its hand-back.
- Tune against the tune split. Report the held-out split only at milestone
  hand-backs.
- A change that lowers the primary score or breaks a guard is reverted, or
  the hand-back names the trade and why it is worth it.
- Readability is judged by OCR engines independent of the detector under
  test. A frame counts only if it is real video: an all-slate or black output
  scores zero.

## Review and merge

Owner decision (2026-10-29, owner queue #42): milestone PRs. For each, the
conductor runs the full gate itself and gives one cross-vendor review (Codex
writes, Opus reviews), then merges. Branches are `elannash/<short-description>`.

## Secrets and publishing

- Twitch credentials come from Infisical through `infisical run --`. The
  stream key is fetched from the Twitch API at runtime and held in memory
  only; it is never written to disk, logs, fixtures or output.
- The repo stays private until the owner approves making it public.
- Pushes to Twitch ingest use bandwidth-test mode (`?bandwidthtest=true`)
  unless the owner has approved a live session.
- Fixtures and video assets are CC0, CC-BY or public domain, listed with
  source and license in `fixtures/ATTRIBUTION.md`. No music.
