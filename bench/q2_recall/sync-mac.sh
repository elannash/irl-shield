#!/usr/bin/env bash
# Run only after root releases the lane. This script never runs a remote test.
set -euo pipefail
recall_root=$(cd "$(dirname "$0")/../.." && pwd)
recall_mirror=/Users/elannash/code/irl-shield-q2-recall-bccad190
ssh mac "bash -lc 'mkdir -p $recall_mirror'"
rsync -az --no-links \
  --exclude='.git' --exclude='.build' --exclude='out' --exclude='.tmp' \
  --exclude='.venv' --exclude='venv' --exclude='__pycache__' \
  --exclude='cache' --exclude='caches' --exclude='.env*' \
  "$recall_root/" "mac:$recall_mirror/"
