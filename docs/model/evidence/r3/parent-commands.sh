#!/bin/bash
# Historical parent commands; this is a receipt, not an authorized rerun.
# Budget extension: conductor granted exactly two calls, total ceiling46.
# Input hashes verified before08; finalTLC is currently running.
# cwd=WORKTREE_t3-3bb00dac
bash /tmp/agents/irl-shield/m3-r3/08-final-tlc.command.sh > /tmp/agents/irl-shield/m3-r3/08-final-tlc.log 2>&1
# 09 is authorized only after08 exits0. It has not been run yet.
# 08 returned exit0: 73,263,001 generated /7,380,396 distinct /0queued, depth43.
# Frozen source hash receipt verified unchanged again before09.
# Parent final authorized invocation: replay then gate in one Python process.
bash /tmp/agents/irl-shield/m3-r3/09-replay-combined-gate.command.sh > /tmp/agents/irl-shield/m3-r3/09-replay-combined-gate.log 2>&1
# 09 returned exit0: public old/final replay PASS,154tests/153passed/1macskip,
# 55/55M3,75.292sec. All frozen source/model/replay hashes verified unchanged.
