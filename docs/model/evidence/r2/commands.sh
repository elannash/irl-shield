#!/bin/bash
# Historical command receipt, not a suite to execute without a fresh budget.
# cwd=WORKTREE_t3-6552b346
# First command (clean exact base; no edits):
# pwd; git branch --show-current; git rev-parse HEAD; git status --short
# Output: cwd above; branch t3/6552b346; ea004ecdad9583996d4907cfb0f35ca130a227af;
# status empty. Host subsequently renamed branch t3/fix-model-release-obligation.
# No git mutation was issued by this worker.
# Source snapshots, shell reads only:
git show ea004ecdad9583996d4907cfb0f35ca130a227af:shield/twitch/events.py > /tmp/agents/irl-shield/m3-r2-model/source-pre/events.py
git show ea004ecdad9583996d4907cfb0f35ca130a227af:shield/control.py > /tmp/agents/irl-shield/m3-r2-model/source-pre/control.py
cp WORKTREE_t3-3bb00dac/shield/twitch/events.py /tmp/agents/irl-shield/m3-r2-model/events-fixed.py
# Hash aa359f9b70a580b768b755febea8433d77ff1402ee6c70771e1967348c92c082
# was supplied by parent before copying, then verified before fixed mapping/run.
# Invocation 1, direct old clamp TLC, expected violation, exit 12:
bash docs/model/evidence/r2/run-tlc.sh old-clamp BeforeR2Control WORKTREE_t3-6552b346/docs/model/evidence/r2/old-clamp.cfg
# Invocation 2, direct fixed TLC:
bash docs/model/evidence/r2/run-tlc.sh fixed-pass TwitchControl WORKTREE_t3-6552b346/docs/model/TwitchControl.cfg
# Invocation 3, combined public old/fixed replay, exit 0:
bash docs/model/evidence/r2/run-public-replay.sh
# Wrappers record the full systemd/nice/JVM/Python commands, without retries.
