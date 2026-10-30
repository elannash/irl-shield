#!/bin/bash
# Receipt only. These invocations have spent the entire four-run allowance.
# No command below authorizes a rerun. Use fresh scratch names if separately approved.
# cwd=/home/elan/.t3/worktrees/irl-shield/t3-39e664cc
# First operation, before edits:
# pwd; git branch --show-current; git rev-parse HEAD; git status --short
# Result: cwd above; t3/r3-raw-timestamp-model;
# 9cb8e812af152833f97adc2ce1cdd4858c5efdf3; empty status.
# git worktree list --porcelain confirmed a different path from the parent.

# Source snapshots (shell reads only):
git show 9cb8e812af152833f97adc2ce1cdd4858c5efdf3:shield/twitch/events.py > /tmp/agents/irl-shield/m3-r3-model/source-pre/events.py
git show 9cb8e812af152833f97adc2ce1cdd4858c5efdf3:shield/control.py > /tmp/agents/irl-shield/m3-r3-model/source-pre/control.py

# Invocation 1, old TLC, exit 255: old-boundary.cfg then had InitialBarrier=-10000.
# Its exact config is archived as old-boundary.config-error.cfg. TLC's config
# parser rejected the negative literal before exploration. This counts as a run.
bash docs/model/evidence/r3/run-tlc.sh old-boundary BeforeR3Control /home/elan/.t3/worktrees/irl-shield/t3-39e664cc/docs/model/evidence/r3/old-boundary.cfg
# Config corrected to InitialBarrier=0; all legal modeled raw stamps are positive.
# Invocation 2, old TLC, expected invariant violation, exit 12:
bash docs/model/evidence/r3/run-tlc.sh old-raw-fail BeforeR3Control /home/elan/.t3/worktrees/irl-shield/t3-39e664cc/docs/model/evidence/r3/old-boundary.cfg

# After parent's explicit freeze and authorization:
cp /home/elan/.t3/worktrees/irl-shield/t3-3bb00dac/shield/twitch/events.py /tmp/agents/irl-shield/m3-r3-model/events-fixed.py
sha256sum /tmp/agents/irl-shield/m3-r3-model/events-fixed.py
# Verified 70345615b503a0f8e03cbdf9da138cdac5f6bc055299d16223ae8692ba896807.
# Invocation 3, fixed TLC, exit 0:
bash docs/model/evidence/r3/run-tlc.sh fixed-raw-pass TwitchControl /home/elan/.t3/worktrees/irl-shield/t3-39e664cc/docs/model/TwitchControl.cfg
# Invocation 4, combined actual old/frozen public replay, exit 0:
bash docs/model/evidence/r3/run-public-replay.sh
# At those invocations the root policy projection/replay were the archived
# TwitchControl-70345615.tla.txt and public_replay-70345615.py.txt. Their exact
# input hashes are in checked-703-inputs.sha256. Neither current final artifact
# was executed. run-tlc-70345615.sh.txt preserves the exact TLC wrapper used.

# Later final source read/mapping only, with NO TLC/Python execution:
cp /tmp/agents/irl-shield/m3-r3-model/events-fixed.py /tmp/agents/irl-shield/m3-r3-model/events-70345615.py
cp /home/elan/.t3/worktrees/irl-shield/t3-3bb00dac/shield/twitch/events.py /tmp/agents/irl-shield/m3-r3-model/events-fixed.py
cp /home/elan/.t3/worktrees/irl-shield/t3-3bb00dac/shield/twitch/transport.py /tmp/agents/irl-shield/m3-r3-model/transport-final.py
sha256sum /tmp/agents/irl-shield/m3-r3-model/events-fixed.py /tmp/agents/irl-shield/m3-r3-model/transport-final.py
# Verified final policy 0e90e43f52b3bd9444925469baf96b40d29480ecefd22c4eeb5afdd68bb630fd
# and transport c0267d0eac1ab7da3b4537b900b4037d53da4645a1e2abb735e5918001a3a426.
# The stronger final model/replay were authored after the four-run cap was spent.

# Read-only live scope evidence, after setting the user-bus address explicitly:
XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
systemctl --user show m3-r3-model-fixed-raw-pass.scope -p ActiveState -p Slice -p MemoryMax -p CPUQuotaPerSecUSec -p ControlGroup
# The first property read lacked these two variables and failed to connect to
# the user bus; it did not launch TLC/Python. The corrected property read worked.

# The wrappers contain the exact systemd/nice/Java/Python invocation, with no
# downloader, scaffolder, automatic retries, mutation flags or invariant removal.
