# IRL Shield

Your IRL stream, minus the street signs.

IRL Shield runs on a Mac between your phone and Twitch. Moblin on the phone
sends RTMP over Tailscale; the Shield masks readable location text with Apple
Vision and publishes to Twitch with about a second of delay. If processing
falls behind, it shows a privacy slate instead of raw video. Mods can type
`!shield hold` in chat to cut to the slate.

Built with OpenAI Codex for the Codex x TwitchCon hackathon. Setup and usage
instructions arrive with the first working build.
