# TwitchControl

TLC reached 5,312 states, more than the chart budget of 500, so the chart draws only the bug paths: 3 states and 2 arrows.

## NoLIVEWithoutCoverage breaks
The shortest path has 2 steps:
0. connecting: HOLD
1. server welcomes connection: subscribing: HOLD
2. subscriptions ready: LIVE without coverage

## Rules that hold
OnlyBroadcasterResumes, ReconnectNeverReplays, BoundedMemory, NoDeadlock
