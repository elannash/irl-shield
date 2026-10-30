# IRL Shield

Integration proposal for the root README. Keep the qualification paragraph with this pitch until the final evidence changes it.

IRL Shield is an experimental relay that covers readable location clues in an IRL stream before the video reaches viewers. A street name, storefront or house number can appear while the streamer is looking somewhere else. The relay uses a short delay buffer to give its detector lanes time to find and mask that text before the frame is released.

The design combines automatic masking with deliberate holds. Authorized chat commands and Twitch Shield Mode can hold the picture when a streamer or moderator needs a pause. Each hold has its own source, so releasing one does not release the others. Automatic coverage is the goal. Moderator action provides another control when it is needed.

The distinction from an app's built-in blur is where the work happens and how it is checked. IRL Shield is a separate relay with a delayed frame clock and a benchmark that uses detector-independent engines to establish readable input truth. Every output judge can expose a leak. Masks are baked into the outgoing video pixels before egress, so those covered pixels remain covered in downstream recordings and VODs made from that output. Missed text, audio and other clues can still reveal location.

The frame engine is independent of the phone app. Compatibility depends on the app's transport settings and an exercised relay path, rather than a claim that every broadcasting app is supported.

**Current qualification:** the natural-text privacy target has not passed. SRT acceptance remains pending. The verified forwarder's Twitch `tcUrl` acceptance still needs an attended test. The project is an experimental prototype, and the demo must show only behavior backed by its final receipts.

[Run instructions](../docs/RUN.md) · [Measurement contract](../bench/README.md) · [Architecture](../docs/ARCHITECTURE.md)
