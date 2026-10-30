#!/usr/bin/env bash
set -euo pipefail
source_root=$(cd "$(dirname "$0")/../.." && pwd)
# Root invokes only after releasing the phone/GPU barrier. No deletion of remote state.
rsync -a --exclude=.git --exclude=.build --exclude=out --exclude=.tmp \
  --exclude=.venv --exclude=__pycache__ --exclude=cache --exclude=caches \
  "$source_root/" mac:/Users/elannash/code/irl-shield-q2-temporal-26ca396c/
