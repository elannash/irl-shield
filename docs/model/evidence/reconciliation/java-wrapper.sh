#!/bin/sh
ledger=/tmp/agents/irl-shield/m3-reconcile-model/java-invocations.log
budget=/tmp/agents/irl-shield/m3-reconcile-model/tlc-invocations.log
printf '%s\n' "$*" >> "$ledger"
case " $* " in
  *' tlc2.TLC '*)
    used=0
    if [ -f "$budget" ]; then used=$(wc -l < "$budget"); fi
    if [ "$used" -ge 3 ]; then
      echo 'Refusing TLC invocation beyond the three-run continuation budget' >&2
      exit 98
    fi
    printf '%s\n' "$*" >> "$budget"
    ;;
esac
exec OWNER_HOME/.local/share/mise/installs/java/temurin-25/bin/java "$@"
