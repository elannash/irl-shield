#!/usr/bin/env bash
# Source-only sync to this lane's dedicated mirror; no Mac process is started.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
[[ $(basename "$root") == t3-5e31c93b ]] || {
  echo 'Run from the assigned precision worktree' >&2
  exit 2
}
rsync -a --exclude=.git --exclude=.build --exclude=out --exclude=.tmp \
  --exclude=.venv --exclude=__pycache__ --exclude=cache --exclude=caches \
  "$root/" mac:/Users/elannash/code/irl-shield-q2-precision-5e31c93b/
