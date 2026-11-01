#!/bin/bash
set -u
# One direct TLC invocation per call; no automatic invariant-removal reruns.
task_root=/tmp/agents/irl-shield/m3-r1-model
model_root=$(cd "$(dirname "$0")/../.." && pwd)
name=$1
spec=$2
config=$3
mkdir -p "$task_root/$name"
cp "$model_root/ControlEnvironment.tla" "$model_root/$spec.tla" "$task_root/"
cp "$config" "$task_root/$name.cfg"
printf '%s\n' "$name direct TLC $spec $config" >> "$task_root/invocations.log"
cd "$task_root"
XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
systemd-run --user --scope --unit="m3-r1-model-$name" --slice=app-t3code-agents.slice \
  -p MemoryMax=2G -p CPUQuota=200% nice -n 10 \
  env JAVA_TOOL_OPTIONS='-Xmx1g -XX:ActiveProcessorCount=2' \
  OWNER_HOME/.local/share/mise/installs/java/temurin-25/bin/java \
  -cp OWNER_HOME/.local/share/mise/installs/http-tla2tools/1.7.4/tla2tools.jar \
  tlc2.TLC -workers 1 -fp 0 -lncheck final -metadir "$task_root/$name/states" \
  -config "$task_root/$name.cfg" "$task_root/$spec.tla" \
  > "$model_root/evidence/r1/$name.tlc.log" 2>&1
result=$?
printf 'exit=%s\n' "$result" >> "$model_root/evidence/r1/$name.tlc.log"
tail -15 "$model_root/evidence/r1/$name.tlc.log"
exit "$result"
