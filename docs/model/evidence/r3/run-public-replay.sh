#!/bin/bash
set -u
task_root=/tmp/agents/irl-shield/m3-r3-model
model_root=$(cd "$(dirname "$0")/../.." && pwd)
printf '%s\n' 'public-replay Python old/fixed public API' >> "$task_root/invocations.log"
XDG_RUNTIME_DIR="/run/user/$(id -u)" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus" \
systemd-run --user --scope --unit=m3-r3-model-public-replay --slice=app-t3code-agents.slice \
  -p MemoryMax=2G -p CPUQuota=200% nice -n 10 \
  /usr/bin/python3 -B -I "$model_root/evidence/r3/public_replay.py" \
  > "$model_root/evidence/r3/public-replay.log" 2>&1
result=$?
printf 'exit=%s\n' "$result" >> "$model_root/evidence/r3/public-replay.log"
tail -18 "$model_root/evidence/r3/public-replay.log"
exit "$result"
