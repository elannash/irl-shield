#!/bin/sh
printf '%s\n' "$*" >> /tmp/agents/irl-shield/m3-model/java-invocations.log
exec OWNER_HOME/.local/share/mise/installs/java/temurin-25/bin/java "$@"
