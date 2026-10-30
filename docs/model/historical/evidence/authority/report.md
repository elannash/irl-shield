# TwitchControl

TLC reached 6,488 states, more than the chart budget of 500, so the chart draws only the bug paths: 4 states and 4 arrows.

## OnlyBroadcasterResumes breaks
The shortest path has 5 steps:
0. connecting: HOLD
1. server welcomes connection: subscribing: HOLD
2. subscriptions ready: ready: PROTECT
3. time advances: ready: PROTECT
4. time advances: ready: PROTECT
5. notification arrives: Moderator resume executed

## Rules that hold
NoLIVEWithoutCoverage, ReconnectNeverReplays, BoundedMemory, NoDeadlock
