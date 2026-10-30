#!/bin/bash
# Record of commands actually executed, in order. Do not execute as another suite.
# cwd=/home/elan/.t3/worktrees/irl-shield/t3-a33f9dc3
# Source snapshots (shell reads/copies, not test invocations):
git show bb6948b9793e1bbb505e84e8042357818ddb9608:shield/twitch/events.py > /tmp/agents/irl-shield/m3-r1-model/source-pre/events.py
git show bb6948b9793e1bbb505e84e8042357818ddb9608:shield/control.py > /tmp/agents/irl-shield/m3-r1-model/source-pre/control.py
git show bb6948b9793e1bbb505e84e8042357818ddb9608:shield/twitch/transport.py > /tmp/agents/irl-shield/m3-r1-model/source-pre/transport.py
# Invocation 1 (exit 12):
bash docs/model/evidence/r1/run-tlc.sh stale-welcome PreFixControl /home/elan/.t3/worktrees/irl-shield/t3-a33f9dc3/docs/model/evidence/r1/stale-welcome.cfg
# Invocation 2 (exit 12):
bash docs/model/evidence/r1/run-tlc.sh dropped-hold PreFixControl /home/elan/.t3/worktrees/irl-shield/t3-a33f9dc3/docs/model/evidence/r1/dropped-hold.cfg
# Frozen integrated source confirmed/captured before the fixed check:
cp /home/elan/.t3/worktrees/irl-shield/t3-3bb00dac/shield/twitch/events.py /tmp/agents/irl-shield/m3-r1-model/events-fixed.py
# Invocation 3 (exit 255): TwitchControl.cfg then contained the preserved
# evidence/r1/fixed-configuration-error.cfg.txt bytes, including {-1,9,11,41}.
bash docs/model/evidence/r1/run-tlc.sh fixed TwitchControl /home/elan/.t3/worktrees/irl-shield/t3-a33f9dc3/docs/model/TwitchControl.cfg
# Invocation 4 (exit 0): final cfg contains {0,9,11,41}; invalid class uses 0.
bash docs/model/evidence/r1/run-tlc.sh fixed-pass TwitchControl /home/elan/.t3/worktrees/irl-shield/t3-a33f9dc3/docs/model/TwitchControl.cfg
# Invocation 5 (exit 0):
bash docs/model/evidence/r1/run-public-replay.sh
# run-tlc.sh and run-public-replay.sh preserve exact resource-limited commands.
