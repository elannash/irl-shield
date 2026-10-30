# TwitchControl

TLC reached 29,412 states, more than the chart budget of 500, so the chart draws only the bug paths: 6 states and 7 arrows.

## ReconnectNeverReplays breaks
The shortest path has 7 steps:
0. connecting: HOLD
1. server welcomes connection: subscribing: HOLD
2. subscriptions ready: ready: PROTECT
3. notification arrives: ready: HOLD
4. server requests reconnect: reconnecting: HOLD
5. server welcomes connection: subscribing: HOLD
6. subscriptions ready: ready: HOLD
7. notification arrives: Repeated command executed

## Rules that hold
NoLIVEWithoutCoverage, OnlyBroadcasterResumes, BoundedMemory, NoDeadlock
