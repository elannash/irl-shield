# Devpost draft

Prepared factual copy for owner editing. No submission, account access or publication has occurred. Final script and voiceover belong to the owner and Opus.

## Project name

IRL Shield

## Tagline

Automatic location-text masking before an IRL stream reaches viewers.

## Inspiration

An IRL streamer can walk past a readable street sign while watching chat or framing the next shot. A location clue can be on screen before anyone has time to react. IRL Shield explores what a relay can do with a small buffer before it releases that frame.

## What it does

IRL Shield sits between a phone's video feed and the stream output. Detector lanes look for readable location text, and the relay covers detected regions in the video pixels before egress. The delay buffer gives the detectors time to work ahead of presentation. Missing coverage produces a protected picture, and an explicit hold produces a slate.

Authorized Twitch chat commands and Shield Mode can hold the picture. Those holds are tracked independently, so a transport recovery or another resume action cannot silently clear a separate active hold. These controls complement the automatic masking system.

## How it is built

The frame engine accepts timestamped frames independently of the phone's transport. It combines asynchronous detection, motion projection and a delayed presentation clock. The repository includes local run instructions, synthetic tests and a reproducible benchmark.

The benchmark separates detector-independent input truth from output leak detection. All configured output judges can expose a readable leak, including a judge from the detector's own family. A black or all-slate output cannot earn a passing real-video result.

## How Codex was used

Project code was written in the designated Codex build thread and its Codex children during the hackathon window. Codex implemented the relay, masking engine, benchmark and tests. The submission's build segment will use reviewed, sanitized records from that real session, labeled as replay or timelapse, with original timestamps and independently checked commit references.

Codex session ID: [FILL IN: owner-confirmed submitted build session ID, not this child thread ID].

## What makes it different

This is a separate relay with a delay buffer and explicit leak verification. Built-in broadcaster privacy controls can complement it. Its protocol boundary provides a path to support more phone apps, with each app and transport requiring qualification. Covered pixels are already masked in the outgoing feed, including recordings and VODs made from it. This does not protect clues that the system misses.

## Current limits and next steps

The natural-text privacy target has not passed. SRT acceptance is pending, and the verified forwarder's Twitch `tcUrl` acceptance needs an attended test. App support must be stated as a tested matrix. No perfect-privacy claim is justified. Final measured results and the exact demonstrated platform belong here only after their receipts are reviewed.

Demonstration URL: [FILL IN: owner-approved public video under three minutes].
Repository URL and judge access: [FILL IN: owner-approved repository link and access].
Tested platform and final evidence: [FILL IN: final platform, build and receipt references].
